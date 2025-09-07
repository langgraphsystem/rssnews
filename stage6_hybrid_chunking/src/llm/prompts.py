"""
Prompt templates for Gemini 2.5 Flash API interactions.
"""

from typing import Dict, Optional


class ChunkRefinementPrompts:
    """Prompt templates for chunk refinement tasks."""
    
    BASE_REFINEMENT_TEMPLATE = """You are a chunking refinement assistant in a news ingestion pipeline.
Your task: suggest SMALL boundary adjustments and merge decisions for the current chunk WITHOUT editing text.

Constraints:
- Target size ~{target_words} words; overlap allowed.
- NEVER break headings/lists/quotes/tables/code blocks.
- If chunk is too short or continues a sentence/list -> propose merge.
- Only adjust boundaries via "offset_adjust" in range −{max_offset}…+{max_offset} characters.
- If chunk is boilerplate (cookie/footer/nav), action="drop".
- Reply STRICTLY as JSON.

Article title: "{title}"
Source: {source_domain} | Lang: {language} | Published: {published_at}
Chunk index: {chunk_index} | start={char_start} end={char_end}
Prev tail (<=120 chars): "{prev_tail}"
Current (trimmed): "{current_chunk}"
Next head (<=120 chars): "{next_head}"

Respond with JSON:
{{
    "action": "keep | merge_prev | merge_next | drop",
    "offset_adjust": -120..120,
    "semantic_type": "intro|body|list|quote|conclusion|code",
    "confidence": 0.0-1.0,
    "reason": "brief explanation"
}}"""

    SIMPLIFIED_TEMPLATE = """Analyze this text chunk for boundary issues and suggest action:

Target: {target_words} words
Current: {word_count} words
Chunk {chunk_index}: "{text_sample}"

Previous context: "{prev_context}"
Next context: "{next_context}"

Response format (JSON only):
{{
    "action": "keep|merge_prev|merge_next|drop",
    "offset_adjust": 0,
    "semantic_type": "intro|body|list|quote|conclusion|code",
    "confidence": 0.8,
    "reason": "explanation"
}}"""

    QUALITY_FOCUSED_TEMPLATE = """Quality assessment for news article chunk:

Article: "{title}" from {source_domain}
Chunk {chunk_index}/{total_chunks}: {word_count} words

Issues detected: {quality_issues}
Text: "{text_preview}"

Context:
Before: "{prev_context}"
After: "{next_context}"

Provide refinement recommendation as JSON:
{{
    "action": "keep|merge_prev|merge_next|drop",
    "offset_adjust": 0,
    "semantic_type": "{semantic_type}",
    "confidence": 0.0-1.0,
    "reason": "specific issue addressed"
}}"""

    @classmethod
    def build_refinement_prompt(cls,
                              chunk_text: str,
                              chunk_index: int,
                              word_count: int,
                              target_words: int,
                              max_offset: int,
                              article_metadata: Dict,
                              prev_context: str = "",
                              next_context: str = "",
                              quality_issues: Optional[list] = None,
                              template_type: str = "base") -> str:
        """
        Build a refinement prompt based on the specified template type.
        
        Args:
            chunk_text: The chunk text to analyze
            chunk_index: Index of chunk in article
            word_count: Number of words in chunk
            target_words: Target word count
            max_offset: Maximum character offset adjustment
            article_metadata: Article metadata dict
            prev_context: Previous chunk context
            next_context: Next chunk context
            quality_issues: List of detected quality issues
            template_type: Type of template to use
            
        Returns:
            Formatted prompt string
        """
        
        # Prepare common variables
        title = article_metadata.get('title', 'Unknown')
        source_domain = article_metadata.get('source_domain', 'unknown')
        language = article_metadata.get('language', 'en')
        published_at = article_metadata.get('published_at', 'unknown')
        
        # Truncate text for prompt (avoid token limits)
        text_sample = cls._truncate_text(chunk_text, 300)  # ~300 chars
        prev_tail = cls._truncate_text(prev_context, 120, from_end=True)
        next_head = cls._truncate_text(next_context, 120, from_start=True)
        
        if template_type == "simplified":
            return cls.SIMPLIFIED_TEMPLATE.format(
                target_words=target_words,
                word_count=word_count,
                chunk_index=chunk_index,
                text_sample=text_sample,
                prev_context=prev_tail,
                next_context=next_head
            )
        
        elif template_type == "quality_focused":
            issues_str = ", ".join(quality_issues) if quality_issues else "none"
            semantic_type = article_metadata.get('semantic_type', 'body')
            total_chunks = article_metadata.get('total_chunks', chunk_index + 1)
            
            return cls.QUALITY_FOCUSED_TEMPLATE.format(
                title=title,
                source_domain=source_domain,
                chunk_index=chunk_index,
                total_chunks=total_chunks,
                word_count=word_count,
                quality_issues=issues_str,
                text_preview=text_sample,
                prev_context=prev_tail,
                next_context=next_head,
                semantic_type=semantic_type
            )
        
        else:  # Default to base template
            # Calculate character positions (if available)
            char_start = article_metadata.get('char_start', 0)
            char_end = article_metadata.get('char_end', len(chunk_text))
            
            return cls.BASE_REFINEMENT_TEMPLATE.format(
                target_words=target_words,
                max_offset=max_offset,
                title=title,
                source_domain=source_domain,
                language=language,
                published_at=published_at,
                chunk_index=chunk_index,
                char_start=char_start,
                char_end=char_end,
                prev_tail=prev_tail,
                current_chunk=text_sample,
                next_head=next_head
            )
    
    @staticmethod
    def _truncate_text(text: str, 
                      max_chars: int, 
                      from_start: bool = True, 
                      from_end: bool = False) -> str:
        """Truncate text to fit within character limit."""
        if not text or len(text) <= max_chars:
            return text
        
        if from_end:
            return "..." + text[-(max_chars-3):]
        elif from_start:
            return text[:max_chars-3] + "..."
        else:
            # Truncate from middle
            half = (max_chars - 3) // 2
            return text[:half] + "..." + text[-half:]


class ValidationPrompts:
    """Prompts for validating LLM responses."""
    
    RESPONSE_VALIDATION_TEMPLATE = """Validate this JSON response for chunk refinement:

Response: {response_json}
Original chunk: {word_count} words
Context: chunk {chunk_index} from {source_domain}

Check for:
1. Valid JSON format
2. Required fields: action, offset_adjust, semantic_type, confidence, reason
3. Valid action values: keep, merge_prev, merge_next, drop
4. offset_adjust in range [-120, 120]
5. confidence in range [0.0, 1.0]
6. semantic_type in: intro, body, list, quote, conclusion, code

Return validation result as JSON:
{{
    "valid": true/false,
    "errors": ["list of specific errors"],
    "warnings": ["list of warnings"],
    "confidence_adjusted": 0.0-1.0
}}"""


class ErrorRecoveryPrompts:
    """Prompts for error recovery and fallback scenarios."""
    
    SIMPLE_FALLBACK_TEMPLATE = """Simple chunk analysis (fallback mode):

Text: "{text_sample}"
Length: {word_count} words (target: {target_words})

Quick assessment - respond with single word:
- "keep" if chunk seems reasonable
- "short" if too short and should merge
- "long" if too long and needs splitting  
- "drop" if appears to be boilerplate/navigation

Response: """

    BINARY_DECISION_TEMPLATE = """Binary decision needed:

Chunk: "{text_preview}"
Issue: {primary_issue}

Should this chunk be processed by LLM? Reply "yes" or "no" only."""

    @classmethod
    def build_fallback_prompt(cls,
                            chunk_text: str,
                            word_count: int,
                            target_words: int,
                            primary_issue: str = "quality") -> str:
        """Build a simple fallback prompt for error recovery."""
        
        text_sample = chunk_text[:200] + "..." if len(chunk_text) > 200 else chunk_text
        
        return cls.SIMPLE_FALLBACK_TEMPLATE.format(
            text_sample=text_sample,
            word_count=word_count,
            target_words=target_words
        )
    
    @classmethod
    def build_binary_prompt(cls,
                          chunk_text: str,
                          primary_issue: str) -> str:
        """Build a binary decision prompt."""
        
        text_preview = chunk_text[:150] + "..." if len(chunk_text) > 150 else chunk_text
        
        return cls.BINARY_DECISION_TEMPLATE.format(
            text_preview=text_preview,
            primary_issue=primary_issue
        )


# Prompt selection utilities

def select_optimal_prompt(chunk_metadata: Dict, 
                         quality_issues: list,
                         api_context: Dict) -> str:
    """
    Select the most appropriate prompt template based on context.
    
    Args:
        chunk_metadata: Chunk metadata including size, type, etc.
        quality_issues: List of detected quality issues
        api_context: API context (token limits, retry count, etc.)
        
    Returns:
        Template type identifier
    """
    # Check API context for constraints
    retry_count = api_context.get('retry_count', 0)
    token_limit_reached = api_context.get('token_limit_reached', False)
    
    # Use simplified prompts for retries or token constraints
    if retry_count > 1 or token_limit_reached:
        return "simplified"
    
    # Use quality-focused prompts for chunks with specific issues
    if len(quality_issues) > 2:
        return "quality_focused"
    
    # Use base template by default
    return "base"


def estimate_prompt_tokens(prompt: str) -> int:
    """
    Estimate token count for a prompt.
    
    Args:
        prompt: Prompt string
        
    Returns:
        Estimated token count
    """
    # Simple estimation: ~4 characters per token for English
    return len(prompt) // 4


def optimize_prompt_length(prompt: str, max_tokens: int = 1500) -> str:
    """
    Optimize prompt length to fit within token limits.
    
    Args:
        prompt: Original prompt
        max_tokens: Maximum allowed tokens
        
    Returns:
        Optimized prompt
    """
    estimated_tokens = estimate_prompt_tokens(prompt)
    
    if estimated_tokens <= max_tokens:
        return prompt
    
    # Truncate while preserving structure
    max_chars = max_tokens * 4
    
    # Find natural truncation points
    lines = prompt.split('\n')
    truncated_lines = []
    current_length = 0
    
    for line in lines:
        if current_length + len(line) > max_chars:
            # Try to preserve important sections
            if 'JSON' in line or 'Response' in line or 'format' in line.lower():
                truncated_lines.append(line)
            break
        truncated_lines.append(line)
        current_length += len(line) + 1  # +1 for newline
    
    return '\n'.join(truncated_lines)