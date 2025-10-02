"""
Policy Layer v1 — Centralized validation for all agent outputs
Enforces: evidence-required, lengths, PII-safety, domain whitelist, schema compliance
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from schemas.analysis_schemas import (
    BaseAnalysisResponse, Insight, Evidence, EvidenceRef,
    PolicyValidator as SchemaValidator
)

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Raised when validation fails"""
    def __init__(self, code: str, user_msg: str, tech_msg: str):
        self.code = code
        self.user_message = user_msg
        self.tech_message = tech_msg
        super().__init__(tech_msg)


class PolicyValidator:
    """Centralized validator for all Phase 1 outputs"""

    # Maximum lengths (enforced strictly)
    MAX_TLDR = 220
    MAX_INSIGHT = 180
    MAX_SNIPPET = 240
    MAX_HEADER = 100

    # Minimum requirements
    MIN_INSIGHTS = 1
    MAX_INSIGHTS = 5
    MIN_EVIDENCE = 1

    def __init__(self):
        self.schema_validator = SchemaValidator()

    def validate_response(self, response: BaseAnalysisResponse) -> Tuple[bool, Optional[str]]:
        """
        Validate complete response against all policies
        Returns: (is_valid, error_message)
        """
        try:
            # 1. Length validation
            self._validate_lengths(response)

            # 2. Evidence required
            self._validate_evidence_required(response.insights)

            # 3. PII/secrets check
            self._validate_pii_safety(response)

            # 4. Domain safety
            self._validate_domain_safety(response.evidence)

            # 5. Schema compliance (structure)
            self._validate_schema_compliance(response)

            # 6. Language consistency
            self._validate_language_consistency(response)

            logger.info(f"✅ Validation passed for correlation_id={response.meta.correlation_id}")
            return True, None

        except ValidationError as e:
            logger.warning(f"❌ Validation failed: {e.code} - {e.user_message}")
            return False, e.user_message
        except Exception as e:
            logger.error(f"❌ Unexpected validation error: {e}")
            return False, f"Validation error: {str(e)}"

    def _validate_lengths(self, response: BaseAnalysisResponse) -> None:
        """Validate all length constraints"""
        # Header
        if len(response.header) > self.MAX_HEADER:
            raise ValidationError(
                "VALIDATION_FAILED",
                "Response header too long",
                f"Header length {len(response.header)} exceeds {self.MAX_HEADER}"
            )

        # TL;DR
        if len(response.tldr) > self.MAX_TLDR:
            raise ValidationError(
                "VALIDATION_FAILED",
                "Summary too long",
                f"TL;DR length {len(response.tldr)} exceeds {self.MAX_TLDR}"
            )

        # Insights
        if len(response.insights) < self.MIN_INSIGHTS:
            raise ValidationError(
                "VALIDATION_FAILED",
                "Insufficient insights",
                f"Need at least {self.MIN_INSIGHTS} insight"
            )

        if len(response.insights) > self.MAX_INSIGHTS:
            raise ValidationError(
                "VALIDATION_FAILED",
                "Too many insights",
                f"Max {self.MAX_INSIGHTS} insights allowed"
            )

        for i, insight in enumerate(response.insights):
            if len(insight.text) > self.MAX_INSIGHT:
                raise ValidationError(
                    "VALIDATION_FAILED",
                    f"Insight {i+1} too long",
                    f"Insight text length {len(insight.text)} exceeds {self.MAX_INSIGHT}"
                )

        # Evidence snippets
        for i, ev in enumerate(response.evidence):
            if len(ev.snippet) > self.MAX_SNIPPET:
                raise ValidationError(
                    "VALIDATION_FAILED",
                    f"Evidence snippet {i+1} too long",
                    f"Snippet length {len(ev.snippet)} exceeds {self.MAX_SNIPPET}"
                )

    def _validate_evidence_required(self, insights: List[Insight]) -> None:
        """Ensure every insight has at least 1 evidence_ref"""
        for i, insight in enumerate(insights):
            if not insight.evidence_refs or len(insight.evidence_refs) == 0:
                raise ValidationError(
                    "VALIDATION_FAILED",
                    f"Insight {i+1} missing evidence",
                    f"Insight '{insight.text[:50]}...' has no evidence_refs (required)"
                )

            # Validate evidence_ref structure
            for ref in insight.evidence_refs:
                if not ref.date:
                    raise ValidationError(
                        "VALIDATION_FAILED",
                        f"Evidence reference missing date",
                        f"Evidence_ref in insight {i+1} missing required date field"
                    )

                # Date format validation (YYYY-MM-DD)
                if not re.match(r'^\d{4}-\d{2}-\d{2}$', ref.date):
                    raise ValidationError(
                        "VALIDATION_FAILED",
                        "Invalid evidence date format",
                        f"Date {ref.date} must be YYYY-MM-DD format"
                    )

    def _validate_pii_safety(self, response: BaseAnalysisResponse) -> None:
        """Check for PII patterns in all text fields"""
        # Check TL;DR
        if self.schema_validator.contains_pii(response.tldr):
            raise ValidationError(
                "VALIDATION_FAILED",
                "Response contains sensitive information",
                f"PII detected in TL;DR"
            )

        # Check insights
        for i, insight in enumerate(response.insights):
            if self.schema_validator.contains_pii(insight.text):
                raise ValidationError(
                    "VALIDATION_FAILED",
                    "Insight contains sensitive information",
                    f"PII detected in insight {i+1}"
                )

        # Check evidence snippets
        for i, ev in enumerate(response.evidence):
            if self.schema_validator.contains_pii(ev.snippet):
                raise ValidationError(
                    "VALIDATION_FAILED",
                    "Evidence contains sensitive information",
                    f"PII detected in evidence snippet {i+1}"
                )

    def _validate_domain_safety(self, evidence: List[Evidence]) -> None:
        """Validate all evidence sources are from safe domains"""
        for i, ev in enumerate(evidence):
            if not self.schema_validator.is_safe_domain(ev.url):
                raise ValidationError(
                    "VALIDATION_FAILED",
                    f"Evidence from untrusted source",
                    f"Evidence {i+1} from blacklisted domain: {ev.url}"
                )

            # Additional URL validation
            if ev.url and not ev.url.startswith(('http://', 'https://')):
                raise ValidationError(
                    "VALIDATION_FAILED",
                    "Invalid evidence URL",
                    f"Evidence {i+1} URL must start with http:// or https://"
                )

    def _validate_schema_compliance(self, response: BaseAnalysisResponse) -> None:
        """Validate schema structure compliance"""
        # Check required fields exist
        if not response.header:
            raise ValidationError(
                "VALIDATION_FAILED",
                "Missing response header",
                "header field is required"
            )

        if not response.tldr:
            raise ValidationError(
                "VALIDATION_FAILED",
                "Missing summary",
                "tldr field is required"
            )

        if not response.insights:
            raise ValidationError(
                "VALIDATION_FAILED",
                "Missing insights",
                "At least 1 insight is required"
            )

        if not response.evidence:
            raise ValidationError(
                "VALIDATION_FAILED",
                "Missing evidence",
                "At least 1 evidence item is required"
            )

        if not response.result:
            raise ValidationError(
                "VALIDATION_FAILED",
                "Missing analysis results",
                "result field is required"
            )

        # Check meta fields
        if not response.meta.model:
            raise ValidationError(
                "VALIDATION_FAILED",
                "Missing model information",
                "meta.model is required"
            )

        if not response.meta.correlation_id:
            raise ValidationError(
                "VALIDATION_FAILED",
                "Missing correlation ID",
                "meta.correlation_id is required"
            )

    def _validate_language_consistency(self, response: BaseAnalysisResponse) -> None:
        """Validate language consistency (header/tldr should match query language)"""
        # For now, just check they're not empty
        # Future: add language detection and consistency checks
        pass

    def validate_result_schema(self, result: Dict[str, Any], result_type: str) -> Tuple[bool, Optional[str]]:
        """
        Validate agent-specific result schema
        result_type: "keyphrases" | "sentiment" | "topics" | "trends" | "agentic" | "events" | "graph" | "synthesis" | "memory" | "forecast" | "competitors" | "synthesis"
        """
        try:
            if result_type == "keyphrases":
                self._validate_keyphrase_result(result)
            elif result_type == "sentiment":
                self._validate_sentiment_result(result)
            elif result_type == "topics":
                self._validate_topic_result(result)
            elif result_type == "trends":
                self._validate_trends_result(result)
            # Phase 2: NEW result types
            elif result_type == "forecast":
                self._validate_forecast_result(result)
            elif result_type == "competitors":
                self._validate_competitors_result(result)
            elif result_type == "synthesis":
                self._validate_synthesis_result(result)
            else:
                raise ValidationError(
                    "INTERNAL",
                    "Unknown result type",
                    f"Result type {result_type} not supported"
                )

            return True, None

        except ValidationError as e:
            return False, e.user_message
        except Exception as e:
            return False, f"Result validation error: {str(e)}"

    def _validate_keyphrase_result(self, result: Dict[str, Any]) -> None:
        """Validate KeyphraseMining result"""
        if "keyphrases" not in result:
            raise ValidationError(
                "VALIDATION_FAILED",
                "Missing keyphrases",
                "keyphrases field required in result"
            )

        if not result["keyphrases"]:
            raise ValidationError(
                "VALIDATION_FAILED",
                "No keyphrases found",
                "keyphrases list is empty"
            )

    def _validate_sentiment_result(self, result: Dict[str, Any]) -> None:
        """Validate SentimentEmotion result"""
        required_fields = ["overall", "emotions"]
        for field in required_fields:
            if field not in result:
                raise ValidationError(
                    "VALIDATION_FAILED",
                    f"Missing {field}",
                    f"{field} field required in sentiment result"
                )

        # Validate overall score range
        if not (-1.0 <= result["overall"] <= 1.0):
            raise ValidationError(
                "VALIDATION_FAILED",
                "Invalid sentiment score",
                f"overall sentiment {result['overall']} must be in [-1, 1]"
            )

    def _validate_topic_result(self, result: Dict[str, Any]) -> None:
        """Validate TopicModeler result"""
        if "topics" not in result:
            raise ValidationError(
                "VALIDATION_FAILED",
                "Missing topics",
                "topics field required in result"
            )

        if not result["topics"]:
            raise ValidationError(
                "VALIDATION_FAILED",
                "No topics found",
                "topics list is empty"
            )

    def _validate_trends_result(self, result: Dict[str, Any]) -> None:
        """Validate TrendsEnhanced result"""
        required_fields = ["topics", "sentiment"]
        for field in required_fields:
            if field not in result:
                raise ValidationError(
                    "VALIDATION_FAILED",
                    f"Missing {field}",
                    f"{field} field required in trends result"
                )

    # ========================================================================
    # Phase 2: Result Validators
    # ========================================================================

    def _validate_forecast_result(self, result: Dict[str, Any]) -> None:
        """Validate TrendForecaster result (Phase 2)"""
        if "forecast" not in result:
            raise ValidationError(
                "VALIDATION_FAILED",
                "Missing forecast data",
                "forecast field required in result"
            )

        forecast_items = result["forecast"]
        if not forecast_items or len(forecast_items) == 0:
            raise ValidationError(
                "VALIDATION_FAILED",
                "Empty forecast",
                "forecast list cannot be empty"
            )

        # Validate each forecast item
        for i, item in enumerate(forecast_items):
            # Check required fields
            required = ["topic", "direction", "confidence_interval", "drivers", "horizon"]
            for field in required:
                if field not in item:
                    raise ValidationError(
                        "VALIDATION_FAILED",
                        f"Forecast item {i+1} missing {field}",
                        f"forecast[{i}] missing required field '{field}'"
                    )

            # Validate direction
            if item["direction"] not in ["up", "down", "flat"]:
                raise ValidationError(
                    "VALIDATION_FAILED",
                    "Invalid forecast direction",
                    f"direction must be up/down/flat, got '{item['direction']}'"
                )

            # Validate confidence_interval
            ci = item["confidence_interval"]
            if not isinstance(ci, (list, tuple)) or len(ci) != 2:
                raise ValidationError(
                    "VALIDATION_FAILED",
                    "Invalid confidence interval",
                    f"confidence_interval must be [lower, upper], got {ci}"
                )

            # Validate drivers (must have evidence)
            drivers = item["drivers"]
            if not drivers or len(drivers) == 0:
                raise ValidationError(
                    "VALIDATION_FAILED",
                    "No forecast drivers",
                    f"forecast[{i}] must have at least 1 driver"
                )

            for driver in drivers:
                if "evidence_ref" not in driver:
                    raise ValidationError(
                        "VALIDATION_FAILED",
                        "Driver missing evidence",
                        "All forecast drivers must have evidence_ref"
                    )

    def _validate_competitors_result(self, result: Dict[str, Any]) -> None:
        """Validate CompetitorNews result (Phase 2)"""
        required_fields = ["positioning", "top_domains"]
        for field in required_fields:
            if field not in result:
                raise ValidationError(
                    "VALIDATION_FAILED",
                    f"Missing {field}",
                    f"{field} field required in competitors result"
                )

        # Validate positioning (must have at least 1)
        positioning = result["positioning"]
        if not positioning or len(positioning) == 0:
            raise ValidationError(
                "VALIDATION_FAILED",
                "No competitive positioning",
                "positioning list cannot be empty"
            )

        # Validate positioning items
        for i, pos in enumerate(positioning):
            required = ["domain", "stance", "notes"]
            for field in required:
                if field not in pos:
                    raise ValidationError(
                        "VALIDATION_FAILED",
                        f"Positioning item {i+1} missing {field}",
                        f"positioning[{i}] missing required field '{field}'"
                    )

            # Validate stance
            if pos["stance"] not in ["leader", "fast_follower", "niche"]:
                raise ValidationError(
                    "VALIDATION_FAILED",
                    "Invalid competitive stance",
                    f"stance must be leader/fast_follower/niche, got '{pos['stance']}'"
                )

        # Validate top_domains (must have at least 1)
        if not result["top_domains"] or len(result["top_domains"]) == 0:
            raise ValidationError(
                "VALIDATION_FAILED",
                "No domains found",
                "top_domains list cannot be empty"
            )

    def _validate_synthesis_result(self, result: Dict[str, Any]) -> None:
        """Validate SynthesisAgent result (Phase 2)"""
        required_fields = ["summary", "actions"]
        for field in required_fields:
            if field not in result:
                raise ValidationError(
                    "VALIDATION_FAILED",
                    f"Missing {field}",
                    f"{field} field required in synthesis result"
                )

        # Validate summary (max 400 chars)
        if len(result["summary"]) > 400:
            raise ValidationError(
                "VALIDATION_FAILED",
                "Synthesis summary too long",
                f"summary length {len(result['summary'])} exceeds 400"
            )

        # Validate actions (must have at least 1)
        actions = result["actions"]
        if not actions or len(actions) == 0:
            raise ValidationError(
                "VALIDATION_FAILED",
                "No actions generated",
                "actions list must have at least 1 recommendation"
            )

        # Validate each action
        for i, action in enumerate(actions):
            required = ["recommendation", "impact", "evidence_refs"]
            for field in required:
                if field not in action:
                    raise ValidationError(
                        "VALIDATION_FAILED",
                        f"Action {i+1} missing {field}",
                        f"actions[{i}] missing required field '{field}'"
                    )

            # Validate impact
            if action["impact"] not in ["low", "medium", "high"]:
                raise ValidationError(
                    "VALIDATION_FAILED",
                    "Invalid action impact",
                    f"impact must be low/medium/high, got '{action['impact']}'"
                )

            # Validate evidence (every action needs evidence)
            if not action["evidence_refs"] or len(action["evidence_refs"]) == 0:
                raise ValidationError(
                    "VALIDATION_FAILED",
                    f"Action {i+1} missing evidence",
                    "All actions must have at least 1 evidence_ref"
                )

        # Validate conflicts (if present, must have ≥2 evidence per conflict)
        if "conflicts" in result:
            for i, conflict in enumerate(result["conflicts"]):
                if "evidence_refs" not in conflict:
                    raise ValidationError(
                        "VALIDATION_FAILED",
                        f"Conflict {i+1} missing evidence",
                        "All conflicts must have evidence_refs"
                    )

                if len(conflict["evidence_refs"]) < 2:
                    raise ValidationError(
                        "VALIDATION_FAILED",
                        f"Conflict {i+1} needs more evidence",
                        "Conflicts require at least 2 evidence_refs (contradictory sources)"
                    )


# Singleton instance
_validator_instance = None


def get_validator() -> PolicyValidator:
    """Get singleton validator instance"""
    global _validator_instance
    if _validator_instance is None:
        _validator_instance = PolicyValidator()
    return _validator_instance
    def _validate_agentic_result(self, result: Dict[str, Any]) -> None:
        if "steps" not in result or "answer" not in result:
            raise ValidationError(
                "VALIDATION_FAILED",
                "Missing agentic fields",
                "steps and answer required in agentic result"
            )
        if not result["steps"]:
            raise ValidationError(
                "VALIDATION_FAILED",
                "Empty agentic steps",
                "At least one step required"
            )

    def _validate_events_result(self, result: Dict[str, Any]) -> None:
        if "events" not in result:
            raise ValidationError(
                "VALIDATION_FAILED",
                "Missing events",
                "events field required in events result"
            )
        if not result["events"]:
            raise ValidationError(
                "VALIDATION_FAILED",
                "No events found",
                "events list cannot be empty"
            )

    def _validate_graph_result(self, result: Dict[str, Any]) -> None:
        if "subgraph" not in result or "answer" not in result:
            raise ValidationError(
                "VALIDATION_FAILED",
                "Missing graph subgraph",
                "subgraph and answer required in graph result"
            )
        subgraph = result["subgraph"]
        if "nodes" not in subgraph or "edges" not in subgraph:
            raise ValidationError(
                "VALIDATION_FAILED",
                "Invalid subgraph",
                "subgraph must include nodes and edges"
            )

    def _validate_synthesis_result(self, result: Dict[str, Any]) -> None:
        if "summary" not in result or "actions" not in result:
            raise ValidationError(
                "VALIDATION_FAILED",
                "Missing synthesis fields",
                "summary and actions required in synthesis result"
            )
        if not result["actions"]:
            raise ValidationError(
                "VALIDATION_FAILED",
                "No actions found",
                "At least one action required"
            )

    def _validate_memory_result(self, result: Dict[str, Any]) -> None:
        if "operation" not in result:
            raise ValidationError(
                "VALIDATION_FAILED",
                "Missing memory operation",
                "operation field required in memory result"
            )
