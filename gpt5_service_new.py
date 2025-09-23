"""GPT-5 Service with OpenAI Responses API integration."""

import json
import os
import sys
from typing import Dict, Any, Optional, Union, List

from openai import OpenAI


class GPT5Service:
    """Service for GPT-5 models using OpenAI Responses API."""

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

    def _merge(self, preset_name: str, model_id: str) -> Dict[str, Any]:
        """Merge preset values with request template.

        Args:
            preset_name: Name of preset from config
            model_id: Model identifier

        Returns:
            Merged configuration dictionary

        Raises:
            KeyError: If preset not found in config
        """
        if preset_name not in self.config["presets"]:
            raise KeyError(f"Preset '{preset_name}' not found in config")

        preset = self.config["presets"][preset_name].copy()
        template = self.config["request_template"].copy()

        # Merge preset values into template
        for key, value in preset.items():
            if f"{{{{{key}}}}}" in str(template):
                # Replace placeholder with actual value
                template = json.loads(
                    json.dumps(template).replace(f"{{{{{key}}}}}", str(value))
                )

        return template

    def choose_model(self, task: str) -> str:
        """Choose model ID based on task routing.

        Args:
            task: Task type for routing

        Returns:
            Model ID string, defaults to "gpt-5" if task not found
        """
        return self.config["routing"].get(task, "gpt-5")

    def build_request(
        self,
        message: str,
        model_id: str,
        preset: str = "deterministic",
        stream: bool = False,
        reasoning_effort: Optional[str] = None,
        response_format: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Build request payload for Responses API.

        Args:
            message: User message text
            model_id: Model identifier
            preset: Preset name from config
            stream: Enable streaming
            reasoning_effort: Reasoning effort level
            response_format: Custom response format

        Returns:
            Request payload dictionary

        Raises:
            KeyError: If preset or model not found
        """
        request = self._merge(preset, model_id)

        # Check if model supports reasoning
        model_info = None
        for model in self.config["models"]:
            if model["id"] == model_id:
                model_info = model
                break

        if not model_info:
            raise KeyError(f"Model '{model_id}' not found in config")

        # Replace remaining placeholders
        request_json = json.dumps(request)
        request_json = request_json.replace('"{{model_id}}"', f'"{model_id}"')
        request_json = request_json.replace('"{{message}}"', json.dumps(message))
        request_json = request_json.replace('"{{stream_bool}}"', str(stream).lower())

        # Handle reasoning parameter
        if (reasoning_effort is not None and
            model_info["supports_reasoning_effort"]):
            reasoning_value = json.dumps({"effort": reasoning_effort})
        else:
            reasoning_value = "null"

        request_json = request_json.replace('"{{reasoning_or_null}}"', reasoning_value)

        request = json.loads(request_json)

        # Fix integer types
        if "max_output_tokens" in request:
            request["max_output_tokens"] = int(request["max_output_tokens"])

        # Override response format if provided
        if response_format is not None:
            request["response_format"] = response_format

        return request

    def send(
        self,
        message: str,
        model_id: str = "gpt-5",
        preset: str = "deterministic",
        stream: bool = False,
        reasoning_effort: Optional[str] = None,
        response_format: Optional[Dict[str, Any]] = None
    ) -> Union[str, Dict[str, Any]]:
        """Send message to OpenAI Responses API.

        Args:
            message: User message
            model_id: Model to use
            preset: Configuration preset
            stream: Enable streaming
            reasoning_effort: Reasoning effort level
            response_format: Custom response format

        Returns:
            Response text or JSON depending on response_format

        Raises:
            Exception: For API errors with full error details
        """
        request_payload = self.build_request(
            message=message,
            model_id=model_id,
            preset=preset,
            stream=stream,
            reasoning_effort=reasoning_effort,
            response_format=response_format
        )

        try:
            if stream:
                # Remove stream parameter from payload for streaming
                stream_payload = {k: v for k, v in request_payload.items() if k != 'stream'}

                # Streaming response
                with self.client.responses.stream(**stream_payload) as response_stream:
                    full_text = ""

                    for chunk in response_stream:
                        if hasattr(chunk, 'output_text') and chunk.output_text:
                            text_chunk = chunk.output_text
                            print(text_chunk, end='', flush=True)
                            full_text += text_chunk

                    print()  # New line after streaming
                    return full_text
            else:
                # Regular response
                response = self.client.responses.create(**request_payload)

                if (response_format and
                    response_format.get("type") == "json_schema"):
                    # Return structured JSON
                    return json.loads(response.output_text)
                else:
                    # Return plain text
                    return response.output_text

        except Exception as e:
            # Re-raise with full error details
            error_msg = f"OpenAI API error: {type(e).__name__}: {str(e)}"
            raise Exception(error_msg) from e

    def send_qa(self, message: str, **kwargs) -> Union[str, Dict[str, Any]]:
        """Send QA message using routing."""
        model_id = self.choose_model("qa")
        return self.send(message, model_id=model_id, **kwargs)

    def send_chat(self, message: str, **kwargs) -> Union[str, Dict[str, Any]]:
        """Send chat message using routing."""
        model_id = self.choose_model("chat")
        return self.send(message, model_id=model_id, **kwargs)

    def send_code(self, message: str, **kwargs) -> Union[str, Dict[str, Any]]:
        """Send code message using routing."""
        model_id = self.choose_model("code")
        return self.send(message, model_id=model_id, **kwargs)

    def send_bulk(self, message: str, **kwargs) -> Union[str, Dict[str, Any]]:
        """Send bulk message using routing."""
        model_id = self.choose_model("bulk")
        return self.send(message, model_id=model_id, **kwargs)

    def make_batch_jsonl(
        self,
        inputs: List[Dict[str, Any]],
        outfile: str = "gpt5_batch.jsonl"
    ) -> None:
        """Generate JSONL file for batch processing.

        Args:
            inputs: List of input dictionaries with keys:
                    custom_id, message, model, preset, response_format, reasoning_effort
            outfile: Output filename
        """
        with open(outfile, 'w', encoding='utf-8') as f:
            for input_data in inputs:
                custom_id = input_data["custom_id"]
                message = input_data["message"]
                model = input_data["model"]
                preset = input_data.get("preset", "deterministic")
                response_format = input_data.get("response_format")
                reasoning_effort = input_data.get("reasoning_effort")

                body = self.build_request(
                    message=message,
                    model_id=model,
                    preset=preset,
                    stream=False,
                    reasoning_effort=reasoning_effort,
                    response_format=response_format
                )

                batch_item = {
                    "custom_id": custom_id,
                    "method": "POST",
                    "url": "/v1/responses",
                    "body": body
                }

                f.write(json.dumps(batch_item) + '\n')


if __name__ == "__main__":
    # Demo usage
    if len(sys.argv) > 1:
        message = " ".join(sys.argv[1:])

        try:
            service = GPT5Service()
            response = service.send_chat(message, stream=False)
            print(f"Response: {response}")

        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)

    # Demo: Generate batch JSONL
    try:
        service = GPT5Service()

        batch_inputs = [
            {
                "custom_id": "demo-1",
                "message": "What is artificial intelligence?",
                "model": "gpt-5-mini",
                "preset": "deterministic"
            },
            {
                "custom_id": "demo-2",
                "message": "Write a creative story about robots.",
                "model": "gpt-5",
                "preset": "creative",
                "reasoning_effort": "medium"
            },
            {
                "custom_id": "demo-3",
                "message": "Explain quantum computing in simple terms.",
                "model": "gpt-5-nano",
                "preset": "deterministic"
            }
        ]

        service.make_batch_jsonl(batch_inputs)
        print("Generated gpt5_batch.jsonl")

    except Exception as e:
        print(f"Batch generation error: {e}")