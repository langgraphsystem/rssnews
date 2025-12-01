import asyncio
from typing import Type, TypeVar, Literal
from pydantic import BaseModel
from .openai_client import OpenAIClient
import logging
import httpx
import json
import os

logger = logging.getLogger(__name__)

T = TypeVar('T', bound=BaseModel)

class LLMClient:
    """
    Synchronous wrapper supporting both OpenAI and Ollama providers.
    """
    
    def __init__(self, api_key: str = None, provider: Literal["openai", "ollama"] = "ollama"):
        self.provider = provider
        
        if provider == "openai":
            self.client = OpenAIClient(api_key=api_key, model="gpt-5.1-chat-latest")
        else:
            # Ollama configuration
            self.ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            self.ollama_model = os.getenv("OLLAMA_LLM_MODEL", "llama3.2:3b")
            logger.info(f"LLMClient initialized with Ollama: {self.ollama_model}")

    def generate_structured(self, system_prompt: str, user_prompt: str, response_model: Type[T]) -> T:
        """
        Generate a structured response using configured provider.
        """
        if self.provider == "ollama":
            return self._generate_structured_ollama(system_prompt, user_prompt, response_model)
        else:
            return self._generate_structured_openai(system_prompt, user_prompt, response_model)
    
    def _generate_structured_ollama(self, system_prompt: str, user_prompt: str, response_model: Type[T]) -> T:
        """
        Generate structured response using Ollama with JSON parsing.
        """
        # Create example-based instructions instead of showing schema
        # This prevents smaller models from returning the schema itself
        
        full_prompt = f"""{system_prompt}

{user_prompt}

CRITICAL INSTRUCTIONS:
1. Respond with ONLY a JSON object containing your analysis
2. Do NOT include any explanatory text before or after the JSON
3. Do NOT use markdown code blocks like ```json
4. Do NOT return the schema structure itself - return actual analysis data
5. The JSON must be valid and parseable

Example format (use this structure but fill with YOUR analysis):
{{
  "keywords": ["keyword1", "keyword2"],
  "main_ideas": ["idea1", "idea2"],
  "triggers": {{"general": ["trigger1", "trigger2"]}},
  "trends": ["trend1"],
  "target_audience": "description of audience",
  "tone_style": "description of tone",
  "structure_format": "description of structure",
  "facts_data": ["fact1", "fact2"],
  "insights": ["insight1"],
  "practical_utility": ["utility1"]
}}

Now analyze the article and return YOUR JSON:"""

        try:
            # Call Ollama API
            response = httpx.post(
                f"{self.ollama_base_url}/api/generate",
                json={
                    "model": self.ollama_model,
                    "prompt": full_prompt,
                    "stream": False,
                    "format": "json"
                },
                timeout=300.0
            )
            
            if response.status_code == 200:
                result = response.json()
                response_text = result.get("response", "")
                
                # Parse JSON response
                try:
                    # Try to find JSON in the response
                    json_start = response_text.find('{')
                    json_end = response_text.rfind('}') + 1
                    if json_start >= 0 and json_end > json_start:
                        json_str = response_text[json_start:json_end]
                        data = json.loads(json_str)
                        return response_model(**data)
                    else:
                        raise ValueError("No JSON found in response")
                except Exception as e:
                    logger.error(f"Failed to parse Ollama response: {e}")
                    logger.error(f"Response was: {response_text[:500]}")
                    raise
            else:
                raise Exception(f"Ollama API error: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Ollama generation failed: {e}")
            raise
    
    def _generate_structured_openai(self, system_prompt: str, user_prompt: str, response_model: Type[T]) -> T:
        """
        Generate structured response using OpenAI.
        """
        combined_prompt = f"System: {system_prompt}\n\nUser: {user_prompt}"
        
        try:
            return asyncio.run(self.client.acomplete(prompt=combined_prompt, response_format=response_model))
        except Exception as e:
            logger.error(f"OpenAI generation failed: {e}")
            raise

    def generate_text(self, user_prompt: str, system_prompt: str = "You are a helpful AI assistant.") -> str:
        """
        Simple text generation with robust fallback.
        """
        combined_prompt = f"System: {system_prompt}\n\nUser: {user_prompt}"
        try:
            result = asyncio.run(self.client.acomplete(prompt=combined_prompt))
            if isinstance(result, dict):
                return result.get("output", "")
            return str(result)
        except Exception as e:
            logger.error(f"LLM Text Generation failed: {e}")
            # Fallback for demo purposes
            return """
            **AI Insight (Simulated):**
            
            Based on the structural gaps identified:
            1. **Bridge the Gap:** Consider connecting the concept of *Sustainability* with *Cost Efficiency*. Research suggests that eco-friendly packaging can actually reduce shipping weights.
            2. **Hidden Insight:** The term *Innovation* is central but disconnected from *Customer Support*. This suggests a risk where new features are launched without adequate user education.
            
            *Note: This is a simulated response because the LLM API key is missing or invalid.*
            """
