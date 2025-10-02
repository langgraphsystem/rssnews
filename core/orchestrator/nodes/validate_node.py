"""
Validate Node — Third step: validate agent outputs with Policy Layer
Enforces evidence-required, lengths, PII-safety, domain checks
"""

import logging
from typing import Dict, Any
from core.policies.validators import get_validator
from schemas.analysis_schemas import BaseAnalysisResponse, build_error_response, Meta

logger = logging.getLogger(__name__)


async def validate_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute validation step

    Input state:
        - response_draft: BaseAnalysisResponse (built by format_node)
        - correlation_id: str

    Output state (modifies):
        - validation_passed: bool
        - validation_errors: List[str] (if failed)
    """
    try:
        response_draft = state.get("response_draft")
        correlation_id = state.get("correlation_id", "unknown")

        if not response_draft:
            logger.error("No response_draft to validate")
            state["validation_passed"] = False
            state["validation_errors"] = ["Missing response_draft"]
            return state

        logger.info(f"Validation node: validating response")

        # Get validator
        validator = get_validator()

        # Validate complete response
        is_valid, error_message = validator.validate_response(response_draft)

        if is_valid:
            state["validation_passed"] = True
            logger.info("✅ Validation passed")
        else:
            state["validation_passed"] = False
            state["validation_errors"] = [error_message] if error_message else ["Unknown validation error"]
            logger.warning(f"❌ Validation failed: {error_message}")

        return state

    except Exception as e:
        logger.error(f"Validation node failed: {e}", exc_info=True)
        state["validation_passed"] = False
        state["validation_errors"] = [f"Validation error: {e}"]
        state["error"] = {
            "node": "validate",
            "code": "VALIDATION_FAILED",
            "message": str(e)
        }
        return state