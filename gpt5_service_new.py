"""GPT-5 Service with correct OpenAI API integration."""

import json
import os
import sys
from typing import Dict, Any, Optional, Union, List

from openai import OpenAI


class GPT5Service:
    """Service for GPT-5 models using OpenAI Chat Completions API."""

    def __init__(self, config_path: str = "gpt5.config.json") -> None:
        """Initialize service with config and OpenAI client.

        Args:
            config_path: Path to JSON configuration file

        Raises:
            FileNotFoundError: If config file doesn't exist
            KeyError: If OPENAI_API_KEY environment variable not set
            ValueError: If config JSON is invalid
        """
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_path, 'r', encoding='utf-8') as f:
            try:
                self.config = json.load(f)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON in config file: {e}")

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise KeyError("OPENAI_API_KEY environment variable not set")

        self.client = OpenAI(api_key=api_key)

        # Available GPT-5 models and their requirements
        self.available_models = {
            "gpt-5": {"endpoint": "chat", "temperature": 1, "supports_reasoning": True},
            "gpt-5-mini": {"endpoint": "chat", "temperature": 1, "supports_reasoning": False},
            "gpt-5-nano": {"endpoint": "chat", "temperature": 1, "supports_reasoning": False},
            "gpt-5-chat-latest": {"endpoint": "chat", "temperature": 1, "supports_reasoning": False},
            "gpt-5-codex": {"endpoint": "responses", "temperature": 1, "supports_reasoning": False},
        }

    def choose_model(self, task: str) -> str:
        """Choose model ID based on task routing.

        Args:
            task: Task type for routing

        Returns:
            Model ID string, defaults to "gpt-5-chat-latest" if task not found
        """
        # Updated routing to use available models
        routing = {
            "qa": "gpt-5-chat-latest",
            "code": "gpt-5-codex",
            "chat": "gpt-5-chat-latest",
            "bulk": "gpt-5-nano",
            "analysis": "gpt-5-chat-latest",
            "sentiment": "gpt-5-mini",
            "insights": "gpt-5-chat-latest"
        }
        return routing.get(task, "gpt-5-chat-latest")

    def send_chat_completion(
        self,
        message: str,
        model_id: str = "gpt-5-chat-latest",
        max_completion_tokens: int = 1000,
        stream: bool = False
    ) -> str:
        """Send message using Chat Completions API.

        Args:
            message: User message
            model_id: Model to use
            max_completion_tokens: Maximum tokens in response
            stream: Enable streaming

        Returns:
            Response text

        Raises:
            Exception: For API errors with full error details
        """
        if model_id not in self.available_models:
            raise ValueError(f"Model {model_id} not available. Available: {list(self.available_models.keys())}")

        model_config = self.available_models[model_id]

        if model_config["endpoint"] != "chat":
            raise ValueError(f"Model {model_id} requires responses endpoint, use send_responses instead")

        try:
            if stream:
                # Streaming response
                stream_response = self.client.chat.completions.create(
                    model=model_id,
                    messages=[{"role": "user", "content": message}],
                    max_completion_tokens=max_completion_tokens,
                    temperature=model_config["temperature"],
                    stream=True
                )

                full_text = ""
                for chunk in stream_response:
                    if chunk.choices[0].delta.content:
                        text_chunk = chunk.choices[0].delta.content
                        print(text_chunk, end='', flush=True)
                        full_text += text_chunk

                print()  # New line after streaming
                return full_text
            else:
                # Regular response
                response = self.client.chat.completions.create(
                    model=model_id,
                    messages=[{"role": "user", "content": message}],
                    max_completion_tokens=max_completion_tokens,
                    temperature=model_config["temperature"]
                )

                return response.choices[0].message.content

        except Exception as e:
            # Re-raise with full error details
            error_msg = f"OpenAI API error: {type(e).__name__}: {str(e)}"
            raise Exception(error_msg) from e

    def send_responses_api(
        self,
        message: str,
        model_id: str = "gpt-5-codex",
        reasoning_effort: Optional[str] = None
    ) -> str:
        """Send message using Responses API (for gpt-5-codex).

        Args:
            message: User message
            model_id: Model to use (must support responses API)
            reasoning_effort: Reasoning effort level

        Returns:
            Response text

        Raises:
            Exception: For API errors with full error details
        """
        if model_id not in self.available_models:
            raise ValueError(f"Model {model_id} not available")

        model_config = self.available_models[model_id]

        if model_config["endpoint"] != "responses":
            raise ValueError(f"Model {model_id} requires chat completions endpoint, use send_chat_completion instead")

        try:
            # Build request for responses API
            request_data = {
                "model": model_id,
                "input": message
            }

            # Add reasoning effort if supported
            if reasoning_effort and model_config["supports_reasoning"]:
                request_data["reasoning"] = {"effort": reasoning_effort}

            response = self.client.responses.create(**request_data)
            return response.output_text

        except Exception as e:
            error_msg = f"OpenAI Responses API error: {type(e).__name__}: {str(e)}"
            raise Exception(error_msg) from e

    def send(
        self,
        message: str,
        model_id: str = "gpt-5-chat-latest",
        max_completion_tokens: int = 1000,
        stream: bool = False,
        reasoning_effort: Optional[str] = None
    ) -> str:
        """Send message to appropriate GPT-5 API endpoint.

        Args:
            message: User message
            model_id: Model to use
            max_completion_tokens: Maximum tokens in response
            stream: Enable streaming (only for chat completions)
            reasoning_effort: Reasoning effort level (only for responses API)

        Returns:
            Response text

        Raises:
            Exception: For API errors
        """
        if model_id not in self.available_models:
            # Fallback to available model
            model_id = "gpt-5-chat-latest"

        model_config = self.available_models[model_id]

        if model_config["endpoint"] == "chat":
            return self.send_chat_completion(message, model_id, max_completion_tokens, stream)
        else:
            return self.send_responses_api(message, model_id, reasoning_effort)

    # Convenience methods with routing
    def send_qa(self, message: str, **kwargs) -> str:
        """Send QA message using routing."""
        model_id = self.choose_model("qa")
        return self.send(message, model_id=model_id, **kwargs)

    def send_chat(self, message: str, **kwargs) -> str:
        """Send chat message using routing."""
        model_id = self.choose_model("chat")
        return self.send(message, model_id=model_id, **kwargs)

    def send_code(self, message: str, **kwargs) -> str:
        """Send code message using routing."""
        model_id = self.choose_model("code")
        return self.send(message, model_id=model_id, **kwargs)

    def send_bulk(self, message: str, **kwargs) -> str:
        """Send bulk message using routing."""
        model_id = self.choose_model("bulk")
        return self.send(message, model_id=model_id, **kwargs)

    def send_analysis(self, message: str, **kwargs) -> str:
        """Send analysis message using routing."""
        model_id = self.choose_model("analysis")
        return self.send(message, model_id=model_id, **kwargs)

    def send_sentiment(self, message: str, **kwargs) -> str:
        """Send sentiment analysis message using routing."""
        model_id = self.choose_model("sentiment")
        return self.send(message, model_id=model_id, **kwargs)

    def send_insights(self, message: str, **kwargs) -> str:
        """Send insights message using routing."""
        model_id = self.choose_model("insights")
        return self.send(message, model_id=model_id, **kwargs)

    def list_available_models(self) -> List[str]:
        """List all available GPT-5 models."""
        return list(self.available_models.keys())

    def get_model_info(self, model_id: str) -> Dict[str, Any]:
        """Get information about a specific model."""
        return self.available_models.get(model_id, {})


if __name__ == "__main__":
    # Demo usage
    if len(sys.argv) > 1:
        message = " ".join(sys.argv[1:])

        try:
            service = GPT5Service()
            print(f"Available models: {service.list_available_models()}")

            response = service.send_chat(message, stream=False)
            print(f"Response: {response}")

        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)
    else:
        # Demo: Show available models
        try:
            service = GPT5Service()
            print("🤖 GPT-5 Service Initialized Successfully!")
            print(f"📋 Available models: {service.list_available_models()}")

            # Test each model with a simple message
            test_message = "Say hello in one sentence"

            for model in service.list_available_models():
                print(f"\n🧪 Testing {model}...")
                try:
                    response = service.send(test_message, model_id=model, max_completion_tokens=50)
                    print(f"✅ {model}: {response}")
                except Exception as e:
                    print(f"❌ {model}: {e}")

        except Exception as e:
            print(f"Service initialization error: {e}")