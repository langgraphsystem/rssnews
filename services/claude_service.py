#!/usr/bin/env python3
"""
Claude Service for News Trend Analysis
Integrates with Anthropic's Claude API to provide enhanced trend analysis
"""

import os
import json
import logging
import asyncio
import httpx
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class ClaudeConfig:
    """Configuration for Claude API"""
    api_key: str
    model: str = "claude-3-5-sonnet-20241022"  # Claude Sonnet 4
    max_tokens: int = 4000
    temperature: float = 0.3
    timeout: int = 30

class ClaudeService:
    """Service for integrating with Claude API for news trend analysis"""

    def __init__(self, api_key: str = None, config: ClaudeConfig = None):
        """Initialize Claude service

        Args:
            api_key: Anthropic API key (if not provided, reads from env)
            config: Claude configuration object
        """
        # Get API key from parameter or environment
        self.api_key = api_key or os.getenv('ANTHROPIC_API_KEY')
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY is required - set it in environment or pass as parameter")

        # Set up configuration
        self.config = config or ClaudeConfig(api_key=self.api_key)

        # API endpoint
        self.api_url = "https://api.anthropic.com/v1/messages"

        # Headers for API requests
        self.headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01"
        }

        logger.info(f"✅ Claude Service initialized with model: {self.config.model}")

    async def analyze_trends(self, trends_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze trends using Claude News Trend Analyst

        Args:
            trends_data: Structured trends data in Claude input format

        Returns:
            Claude analysis response in structured format
        """
        try:
            logger.info(f"📊 Sending trends analysis to Claude (model: {self.config.model})")

            # Build the prompt with trends data
            prompt = self._build_analysis_prompt(trends_data)

            # Make API request to Claude
            response = await self._make_api_request(prompt)

            # Parse and validate response
            analysis = self._parse_response(response)

            logger.info(f"✅ Claude analysis completed successfully")
            return analysis

        except Exception as e:
            logger.error(f"❌ Claude analysis failed: {e}")
            raise

    def _build_analysis_prompt(self, trends_data: Dict[str, Any]) -> str:
        """Build the complete prompt for Claude News Trend Analyst

        Args:
            trends_data: Trends data to analyze

        Returns:
            Complete prompt string
        """
        # Convert trends data to JSON string for the prompt
        trends_json = json.dumps(trends_data, indent=2, ensure_ascii=False)

        # The enhanced News Trend Analyst prompt
        prompt = f"""ROLE: You are a PRECISION NEWS TREND ANALYST specializing in data-driven trend identification and risk assessment.

OBJECTIVE: Analyze 24h clustered news data to produce:
(A) Executive-level daily OVERVIEW
(B) Actionable TREND CARDS for top-N clusters ranked by impact

## CRITICAL CONSTRAINTS

### Data Integrity
- NEVER fabricate: sources, headlines, URLs, statistics, or quotes
- Evidence MUST come exclusively from provided "headlines" array
- If insufficient data exists, acknowledge gaps rather than invent

### Content Standards
- Exclude media identifiers: show names, domains, generic terms ("live", "breaking", "vs")
- Maintain journalistic neutrality and factual precision
- Prioritize signal over noise: focus on substantial developments

### Output Requirements
- Return ONLY valid JSON matching exact schema
- Respect all character/word limits strictly
- No additional text, explanations, or markdown

## ANALYSIS FRAMEWORK

### A) DAILY OVERVIEW
Generate comprehensive situational awareness:

1. **headline** (≤12 words): Dominant narrative of the day
2. **summary** (≤120 words): Context, significance, timing rationale
3. **key_themes** (2-5 items): Major topics with relative importance [0-1]
4. **connections** (1-5 items): Inter-theme relationships and trend correlations
5. **watch_items** (2-6 items): Forward-looking monitoring priorities

### B) TREND ENRICHMENT
For top-N trends by score, provide actionable intelligence:

1. **name** (≤12 words): Clear, jargon-free trend identifier
2. **why_now** (1 sentence, ≤32 words): Immediate catalyst explanation
3. **drivers** (2-3 phrases): Primary momentum factors
4. **risks** (1-2 phrases): Countertrends or uncertainties
5. **horizon**: Timeline classification ["now", "3-6m", "6-18m"]
6. **confidence** (0-100): Trend validity assessment
7. **evidence** (1-2 items): Supporting headlines from source data
8. **metrics**: Pass-through statistics from input
9. **relations** (0-3 items): Cross-trend dependencies

## OUTPUT SCHEMA
{{
  "overview": {{
    "headline": "string (≤12 words)",
    "summary": "string (≤120 words)",
    "key_themes": [
      {{ "name": "string (≤6 words)", "weight": 0.8 }}
    ],
    "connections": [
      {{
        "from": "theme_name|trend_id",
        "to": "theme_name|trend_id",
        "rationale": "string (≤18 words)"
      }}
    ],
    "watch_items": ["string (≤10 words)"]
  }},
  "topics": [
    {{
      "id": "string",
      "name": "string (≤12 words)",
      "why_now": "string (≤32 words)",
      "drivers": ["string (≤12 words)", "string (≤12 words)"],
      "risks": ["string (≤12 words)"],
      "horizon": "now|3-6m|6-18m",
      "confidence": 85,
      "evidence": [
        {{ "title": "string", "domain": "string", "url": "https://..." }}
      ],
      "metrics": {{ "count": 0, "delta": 0.0, "source_diversity": 0 }},
      "relations": [
        {{ "to_trend_id": "string", "rationale": "string (≤14 words)" }}
      ]
    }}
  ],
  "meta": {{
    "time_window": "24h",
    "top_n_applied": 5,
    "analysis_timestamp": "{datetime.now().strftime('%Y-%m-%d')}",
    "data_quality_note": "Evidence sourced exclusively from provided headlines"
  }}
}}

## INPUT DATA TO ANALYZE:

{trends_json}

RETURN: Valid JSON only. No additional commentary."""

        return prompt

    async def _make_api_request(self, prompt: str) -> Dict[str, Any]:
        """Make API request to Claude

        Args:
            prompt: The complete prompt to send

        Returns:
            Raw API response
        """
        payload = {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        }

        async with httpx.AsyncClient(timeout=self.config.timeout) as client:
            response = await client.post(
                self.api_url,
                json=payload,
                headers=self.headers
            )

            if response.status_code != 200:
                error_text = response.text
                logger.error(f"Claude API error {response.status_code}: {error_text}")
                raise Exception(f"Claude API error: {response.status_code} - {error_text}")

            return response.json()

    def _parse_response(self, api_response: Dict[str, Any]) -> Dict[str, Any]:
        """Parse and validate Claude API response

        Args:
            api_response: Raw API response from Claude

        Returns:
            Parsed analysis data
        """
        try:
            # Extract content from Claude response format
            content = api_response.get("content", [])
            if not content:
                raise ValueError("No content in Claude response")

            # Get the text content (Claude returns array of content blocks)
            text_content = ""
            for block in content:
                if block.get("type") == "text":
                    text_content += block.get("text", "")

            if not text_content:
                raise ValueError("No text content found in Claude response")

            # Parse JSON from the text content
            analysis = json.loads(text_content.strip())

            # Basic validation
            if not isinstance(analysis, dict):
                raise ValueError("Analysis is not a dictionary")

            required_keys = ["overview", "topics", "meta"]
            for key in required_keys:
                if key not in analysis:
                    raise ValueError(f"Missing required key: {key}")

            logger.debug(f"✅ Successfully parsed Claude response with {len(analysis.get('topics', []))} topics")
            return analysis

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Claude response as JSON: {e}")
            raise ValueError(f"Invalid JSON in Claude response: {e}")
        except Exception as e:
            logger.error(f"Error parsing Claude response: {e}")
            raise

    def validate_analysis(self, analysis: Dict[str, Any]) -> bool:
        """Validate the structure and content of Claude analysis

        Args:
            analysis: Parsed analysis from Claude

        Returns:
            True if valid, False otherwise
        """
        try:
            # Check overview structure
            overview = analysis.get("overview", {})
            if not all(key in overview for key in ["headline", "summary", "key_themes"]):
                return False

            # Check topics structure
            topics = analysis.get("topics", [])
            for topic in topics:
                required_topic_keys = ["id", "name", "why_now", "drivers", "confidence", "evidence", "metrics"]
                if not all(key in topic for key in required_topic_keys):
                    return False

            # Check meta structure
            meta = analysis.get("meta", {})
            if not all(key in meta for key in ["time_window", "analysis_timestamp"]):
                return False

            return True

        except Exception as e:
            logger.error(f"Validation error: {e}")
            return False

    async def ping(self) -> bool:
        """Test connectivity to Claude API

        Returns:
            True if API is accessible, False otherwise
        """
        try:
            simple_prompt = "Respond with just: OK"

            payload = {
                "model": self.config.model,
                "max_tokens": 10,
                "messages": [{"role": "user", "content": simple_prompt}]
            }

            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    self.api_url,
                    json=payload,
                    headers=self.headers
                )

                if response.status_code == 200:
                    logger.info("✅ Claude API ping successful")
                    return True
                else:
                    logger.warning(f"⚠️ Claude API ping failed: {response.status_code}")
                    return False

        except Exception as e:
            logger.error(f"❌ Claude API ping failed: {e}")
            return False

    def get_usage_stats(self) -> Dict[str, Any]:
        """Get usage statistics (placeholder for future implementation)

        Returns:
            Usage statistics dictionary
        """
        return {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "status": "active"
        }

# Factory function for easy instantiation
def create_claude_service(api_key: str = None) -> ClaudeService:
    """Create and return a Claude service instance

    Args:
        api_key: Optional API key (reads from env if not provided)

    Returns:
        Configured Claude service
    """
    return ClaudeService(api_key=api_key)

# Test function
async def test_claude_service():
    """Test Claude service functionality"""
    try:
        # Initialize service
        claude = create_claude_service()

        # Test ping
        if not await claude.ping():
            print("❌ Claude API ping failed")
            return False

        print("✅ Claude service test passed")
        return True

    except Exception as e:
        print(f"❌ Claude service test failed: {e}")
        return False

if __name__ == "__main__":
    # Run test if executed directly
    asyncio.run(test_claude_service())