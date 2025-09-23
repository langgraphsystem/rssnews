"""
GPT-5 LLM service for OpenAI API integration
"""

import os
import json
import logging
import asyncio
import httpx
from typing import List, Dict, Any, Optional, Literal

logger = logging.getLogger(__name__)


class GPT5Service:
    """Service for interacting with OpenAI GPT-5 models"""

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-5"):
        """
        Initialize GPT-5 service

        Args:
            api_key: OpenAI API key (from env OPENAI_API_KEY if not provided)
            model: GPT-5 model variant ("gpt-5", "gpt-5-mini", "gpt-5-nano", "gpt-5-chat-latest")
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key is required. Set OPENAI_API_KEY environment variable.")

        self.model = model
        self.base_url = "https://api.openai.com/v1"
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(120.0),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()

    async def generate_text(
        self,
        prompt: str,
        max_completion_tokens: int = 1000,
        temperature: float = 1.0,
        verbosity: Optional[Literal["low", "medium", "high"]] = None,
        reasoning_effort: Optional[Literal["minimal", "low", "medium", "high"]] = None
    ) -> str:
        """
        Generate text using GPT-5

        Args:
            prompt: Input prompt
            max_completion_tokens: Maximum completion tokens to generate
            temperature: Sampling temperature (only 1.0 supported for GPT-5) (only 1.0 supported for GPT-5)
            verbosity: Response verbosity ("low", "medium", "high")
            reasoning_effort: Reasoning effort level ("minimal", "low", "medium", "high")

        Returns:
            Generated text
        """
        messages = [{"role": "user", "content": prompt}]

        payload = {
            "model": self.model,
            "messages": messages,
            "max_completion_tokens": max_completion_tokens,
            "temperature": temperature
        }

        # Add GPT-5 specific parameters
        if verbosity:
            payload["verbosity"] = verbosity
        if reasoning_effort:
            payload["reasoning_effort"] = reasoning_effort

        try:
            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                json=payload
            )

            if response.status_code != 200:
                error_detail = response.text
                raise Exception(f"OpenAI API error {response.status_code}: {error_detail}")

            data = response.json()
            logger.debug(f"Full API response: {data}")

            if "error" in data:
                raise Exception(f"OpenAI API error: {data['error']['message']}")

            content = data["choices"][0]["message"]["content"]
            logger.debug(f"Generated content: '{content}'")
            return content

        except Exception as e:
            logger.error(f"GPT-5 text generation failed: {e}")
            raise

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        max_completion_tokens: int = 1000,
        temperature: float = 1.0,
        verbosity: Optional[Literal["low", "medium", "high"]] = None,
        reasoning_effort: Optional[Literal["minimal", "low", "medium", "high"]] = None,
        stream: bool = False
    ) -> Dict[str, Any]:
        """
        Chat completion using GPT-5

        Args:
            messages: List of message objects with "role" and "content"
            max_completion_tokens: Maximum completion tokens to generate
            temperature: Sampling temperature (only 1.0 supported for GPT-5)
            verbosity: Response verbosity
            reasoning_effort: Reasoning effort level
            stream: Enable streaming response

        Returns:
            Complete API response
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "max_completion_tokens": max_completion_tokens,
            "temperature": temperature,
            "stream": stream
        }

        # Add GPT-5 specific parameters
        if verbosity:
            payload["verbosity"] = verbosity
        if reasoning_effort:
            payload["reasoning_effort"] = reasoning_effort

        try:
            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                json=payload
            )

            if response.status_code != 200:
                error_detail = response.text
                raise Exception(f"OpenAI API error {response.status_code}: {error_detail}")

            return response.json()

        except Exception as e:
            logger.error(f"GPT-5 chat completion failed: {e}")
            raise

    async def analyze_article(
        self,
        text: str,
        metadata: Dict[str, Any],
        analysis_type: str = "summary"
    ) -> Dict[str, Any]:
        """
        Analyze article using GPT-5

        Args:
            text: Article text
            metadata: Article metadata (title, source, etc.)
            analysis_type: Type of analysis ("summary", "sentiment", "topics", "keywords")

        Returns:
            Analysis results
        """
        title = metadata.get('title', 'Unknown')
        source = metadata.get('source_domain', 'Unknown')

        if analysis_type == "summary":
            prompt = f"""Summarize this news article concisely:

Title: {title}
Source: {source}

Article:
{text}

Provide a 2-3 sentence summary highlighting the key points."""

        elif analysis_type == "sentiment":
            prompt = f"""Analyze the sentiment of this news article:

Title: {title}
Article: {text}

Return sentiment as: positive, negative, or neutral, with a brief explanation."""

        elif analysis_type == "topics":
            prompt = f"""Extract the main topics and themes from this article:

Title: {title}
Article: {text}

Return a list of 3-5 main topics/themes."""

        elif analysis_type == "keywords":
            prompt = f"""Extract important keywords and entities from this article:

Title: {title}
Article: {text}

Return key terms, entities, and important phrases."""

        else:
            raise ValueError(f"Unknown analysis_type: {analysis_type}")

        try:
            result = await self.generate_text(
                prompt=prompt,
                max_completion_tokens=500,
                temperature=1.0,  # GPT-5 only supports temperature=1.0
                verbosity="medium"
            )

            return {
                "analysis_type": analysis_type,
                "result": result,
                "model": self.model,
                "article_id": metadata.get('id'),
                "title": title
            }

        except Exception as e:
            logger.error(f"Article analysis failed for {analysis_type}: {e}")
            return {
                "analysis_type": analysis_type,
                "result": None,
                "error": str(e),
                "model": self.model
            }

    async def create_smart_chunks(
        self,
        text: str,
        metadata: Dict[str, Any],
        target_words: int = 400,
        max_chunks: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Create smart chunks using GPT-5

        Args:
            text: Text to chunk
            metadata: Article metadata
            target_words: Target words per chunk
            max_chunks: Maximum number of chunks

        Returns:
            List of chunk objects
        """
        if not text or len(text) < 100:
            return []

        title = metadata.get('title', '')[:100]
        category = metadata.get('category', 'news')
        language = metadata.get('language', 'en')

        prompt = f"""Analyze this {category} article and split it into logical chunks of ~{target_words} words each.

Title: {title}
Language: {language}

Consider:
- Natural paragraph boundaries
- Topic transitions
- Logical flow of information
- Keep related information together
- Avoid breaking sentences

Text to chunk:
{text}

Return ONLY a JSON array with chunks:
[
    {{"text": "chunk content...", "topic": "brief topic", "type": "intro|body|conclusion"}},
    {{"text": "chunk content...", "topic": "brief topic", "type": "body"}}
]

Maximum {max_chunks} chunks. Focus on quality over quantity."""

        try:
            response = await self.generate_text(
                prompt=prompt,
                max_completion_tokens=2000,
                temperature=1.0,  # GPT-5 only supports temperature=1.0
                verbosity="low"
            )

            chunks = self._parse_chunks_response(response, text, max_chunks)

            logger.info(f"GPT-5 chunking completed: {len(chunks)} chunks")
            return chunks

        except Exception as e:
            logger.error(f"GPT-5 chunking failed: {e}")
            return []

    def _parse_chunks_response(self, response: str, original_text: str, max_chunks: int) -> List[Dict[str, Any]]:
        """Parse GPT-5 response into chunk objects"""
        try:
            # Find JSON in response
            json_start = response.find('[')
            json_end = response.rfind(']') + 1

            if json_start == -1 or json_end <= json_start:
                raise ValueError("No JSON array found in response")

            json_str = response[json_start:json_end]
            chunks_data = json.loads(json_str)

            if not isinstance(chunks_data, list):
                raise ValueError("Expected JSON array")

            chunks = []
            char_offset = 0

            for i, chunk_data in enumerate(chunks_data):
                if i >= max_chunks:
                    break

                if isinstance(chunk_data, str):
                    chunk_data = {'text': chunk_data}

                text_chunk = (chunk_data.get('text') or '').strip()
                if not text_chunk or len(text_chunk) < 20:
                    continue

                # Find position in original text
                chunk_start = original_text.find(text_chunk[:50], char_offset)
                if chunk_start == -1:
                    chunk_start = char_offset

                chunk_end = chunk_start + len(text_chunk)
                char_offset = chunk_end

                word_count = len(text_chunk.split())

                chunk = {
                    'chunk_index': i,
                    'text': text_chunk,
                    'word_count_chunk': word_count,
                    'char_start': chunk_start,
                    'char_end': chunk_end,
                    'semantic_type': chunk_data.get('type', 'body'),
                    'boundary_confidence': 0.95,  # High confidence from GPT-5
                    'llm_topic': chunk_data.get('topic', ''),
                    'chunking_method': 'gpt5'
                }

                chunks.append(chunk)

            return chunks

        except Exception as e:
            logger.error(f"Failed to parse GPT-5 chunks response: {e}")
            return []

    async def test_connection(self) -> bool:
        """Test connection to OpenAI API"""
        try:
            response = await self.generate_text(
                prompt="Test connection. Respond with 'OK'.",
                max_completion_tokens=100,
                temperature=1
            )

            logger.info(f"Test response: '{response}'")
            return response and len(response.strip()) > 0

        except Exception as e:
            logger.error(f"GPT-5 connection test failed: {e}")
            return False

    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the current model"""
        return {
            "model": self.model,
            "provider": "OpenAI",
            "capabilities": [
                "text_generation",
                "chat_completion",
                "article_analysis",
                "smart_chunking"
            ],
            "parameters": {
                "verbosity": ["low", "medium", "high"],
                "reasoning_effort": ["minimal", "low", "medium", "high"],
                "max_tokens": 400000,  # GPT-5 context window
                "temperature_range": [1.0]
            }
        }


# Factory function for easy service creation
def create_gpt5_service(model: str = "gpt-5") -> GPT5Service:
    """Create GPT-5 service instance"""
    return GPT5Service(model=model)


# CLI for testing
async def main():
    """CLI entry point for testing GPT-5 service"""
    import argparse

    parser = argparse.ArgumentParser(description='GPT-5 Service Test CLI')
    parser.add_argument('command', choices=['test', 'generate', 'analyze', 'chunk'],
                       help='Command to run')
    parser.add_argument('--model', default='gpt-5',
                       choices=['gpt-5', 'gpt-5-mini', 'gpt-5-nano', 'gpt-5-chat-latest'],
                       help='GPT-5 model variant')
    parser.add_argument('--prompt', type=str, help='Text prompt for generation')
    parser.add_argument('--text', type=str, help='Text for analysis or chunking')
    parser.add_argument('--analysis-type', default='summary',
                       choices=['summary', 'sentiment', 'topics', 'keywords'],
                       help='Type of analysis')

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Create service
    async with GPT5Service(model=args.model) as service:

        if args.command == 'test':
            success = await service.test_connection()
            print(f"GPT-5 connection test: {'PASSED' if success else 'FAILED'}")

            # Show model info
            info = service.get_model_info()
            print(f"Model info: {json.dumps(info, indent=2)}")

        elif args.command == 'generate':
            if not args.prompt:
                print("Error: --prompt is required for generate command")
                return

            result = await service.generate_text(
                prompt=args.prompt,
                max_completion_tokens=500,
                verbosity="medium"
            )
            print(f"Generated text:\n{result}")

        elif args.command == 'analyze':
            if not args.text:
                print("Error: --text is required for analyze command")
                return

            metadata = {'title': 'Test Article', 'source_domain': 'test.com'}
            result = await service.analyze_article(
                text=args.text,
                metadata=metadata,
                analysis_type=args.analysis_type
            )
            print(f"Analysis result:\n{json.dumps(result, indent=2)}")

        elif args.command == 'chunk':
            if not args.text:
                print("Error: --text is required for chunk command")
                return

            metadata = {'title': 'Test Article', 'category': 'news'}
            chunks = await service.create_smart_chunks(
                text=args.text,
                metadata=metadata
            )
            print(f"Created {len(chunks)} chunks:")
            for i, chunk in enumerate(chunks, 1):
                print(f"{i}. [{chunk['semantic_type']}] {chunk['llm_topic']}")
                print(f"   Words: {chunk['word_count_chunk']}")
                print(f"   Text: {chunk['text'][:100]}...")
                print()


if __name__ == "__main__":
    asyncio.run(main())