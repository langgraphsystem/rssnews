"""
Quality router for determining which chunks need LLM processing.
This module implements intelligent routing decisions based on quality indicators.
"""

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

import structlog

from ..chunking.base_chunker import RawChunk, SemanticType
try:
    from ..config.settings import Settings  # type: ignore
except Exception:  # Avoid hard dependency in test context
    from typing import Any as Settings  # type: ignore

logger = structlog.get_logger(__name__)


@dataclass
class RoutingDecision:
    """Represents a routing decision for a chunk."""
    should_use_llm: bool
    confidence: float  # 0.0-1.0 confidence in the decision
    reasons: List[str]  # List of reasons for the decision
    priority: int  # 1-5, higher = more urgent LLM processing needed
    estimated_tokens: int  # Estimated token count for cost calculation


@dataclass
class QualityIndicators:
    """Quality indicators extracted from chunk analysis."""
    size_score: float  # How close to target size (0.0-1.0)
    boundary_score: float  # How well chunk respects boundaries (0.0-1.0) 
    completeness_score: float  # How complete sentences/structures are (0.0-1.0)
    boilerplate_score: float  # Likelihood of being boilerplate (0.0-1.0)
    semantic_coherence: float  # How semantically coherent (0.0-1.0)
    language_confidence: float  # Language detection confidence (0.0-1.0)
    domain_reputation: float  # Quality reputation of source domain (0.0-1.0)
    

class QualityRouter:
    """
    Intelligent quality router that decides which chunks need LLM processing.
    Uses multiple quality indicators and domain-specific rules.
    """
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.thresholds = settings.quality_router_thresholds
        
        # Domain-specific settings
        self.llm_blacklist = settings.llm_blacklist_domains
        self.llm_whitelist = settings.llm_whitelist_domains
        
        # Compiled regex patterns for performance
        self._sentence_endings = re.compile(r'[.!?]+\s*$')
        self._sentence_beginnings = re.compile(r'^[A-Z]')
        self._incomplete_words = re.compile(r'\b\w{1,2}\s*$')  # Likely truncated words
        self._list_continuations = re.compile(r'^\s*(?:and|or|also|furthermore|moreover)', re.IGNORECASE)
        self._mid_sentence_indicators = re.compile(r'[,;:]\s*$')
        
        # Quality indicators cache
        self._domain_quality_cache: Dict[str, float] = {}
        
        logger.info("QualityRouter initialized", thresholds=self.thresholds)
    
    def route_chunks(self, 
                    chunks: List[RawChunk], 
                    article_metadata: Dict,
                    batch_context: Dict) -> List[Tuple[RawChunk, RoutingDecision]]:
        """
        Route chunks through quality analysis and make LLM decisions.
        
        Args:
            chunks: List of raw chunks to analyze
            article_metadata: Article metadata for context
            batch_context: Batch processing context
            
        Returns:
            List of (chunk, routing_decision) tuples
        """
        if not chunks:
            return []
        
        # Extract article-level context
        source_domain = self._extract_domain(article_metadata.get('url', ''))
        article_quality = article_metadata.get('quality_score', 0.5)
        language_confidence = article_metadata.get('language_confidence', 1.0)
        
        # Check batch-level constraints
        batch_stats = self._analyze_batch_constraints(chunks, batch_context)
        
        routed_chunks = []
        llm_chunks_so_far = 0
        
        for chunk in chunks:
            # Analyze chunk quality
            quality_indicators = self._analyze_chunk_quality(
                chunk, article_metadata, source_domain
            )
            
            # Make routing decision
            decision = self._make_routing_decision(
                chunk, 
                quality_indicators,
                article_quality,
                language_confidence,
                source_domain,
                llm_chunks_so_far,
                batch_stats
            )
            
            if decision.should_use_llm:
                llm_chunks_so_far += 1
            
            routed_chunks.append((chunk, decision))
            
            logger.debug(
                "Chunk routed",
                chunk_index=chunk.index,
                use_llm=decision.should_use_llm,
                reasons=decision.reasons,
                confidence=decision.confidence
            )
        
        # Log routing summary
        total_llm = sum(1 for _, d in routed_chunks if d.should_use_llm)
        logger.info(
            "Batch routing completed",
            total_chunks=len(chunks),
            llm_chunks=total_llm,
            llm_percentage=total_llm / len(chunks) if chunks else 0
        )
        
        return routed_chunks
    
    def _analyze_chunk_quality(self, 
                             chunk: RawChunk, 
                             article_metadata: Dict,
                             source_domain: str) -> QualityIndicators:
        """Analyze chunk quality across multiple dimensions."""
        
        # Size analysis
        target_words = self.settings.chunking.target_words
        size_ratio = chunk.word_count / target_words
        size_score = self._calculate_size_score(size_ratio)
        
        # Boundary analysis
        boundary_score = self._analyze_boundaries(chunk)
        
        # Completeness analysis
        completeness_score = self._analyze_completeness(chunk)
        
        # Boilerplate analysis
        boilerplate_score = self._analyze_boilerplate(chunk)
        
        # Semantic coherence
        semantic_coherence = self._analyze_semantic_coherence(chunk)
        
        # Language confidence (from article metadata)
        language_confidence = article_metadata.get('language_confidence', 1.0)
        
        # Domain reputation
        domain_reputation = self._get_domain_reputation(source_domain)
        
        return QualityIndicators(
            size_score=size_score,
            boundary_score=boundary_score,
            completeness_score=completeness_score,
            boilerplate_score=boilerplate_score,
            semantic_coherence=semantic_coherence,
            language_confidence=language_confidence,
            domain_reputation=domain_reputation
        )
    
    def _make_routing_decision(self, 
                             chunk: RawChunk,
                             quality: QualityIndicators,
                             article_quality: float,
                             language_confidence: float,
                             source_domain: str,
                             llm_chunks_so_far: int,
                             batch_stats: Dict) -> RoutingDecision:
        """Make the final routing decision based on all factors."""
        
        reasons = []
        should_use_llm = False
        confidence = 0.5
        priority = 1
        
        # Domain-based override
        domain_preference = self.settings.should_use_llm_for_domain(source_domain)
        if domain_preference is not None:
            should_use_llm = domain_preference
            reasons.append(f"domain_{'whitelist' if domain_preference else 'blacklist'}")
            confidence = 0.9
            priority = 1 if domain_preference else 0
            
            if not domain_preference:  # Blacklisted domain
                return RoutingDecision(
                    should_use_llm=False,
                    confidence=confidence,
                    reasons=reasons,
                    priority=0,
                    estimated_tokens=0
                )
        
        # Feature flag check
        if not self.settings.features.llm_routing_enabled:
            return RoutingDecision(
                should_use_llm=False,
                confidence=1.0,
                reasons=["llm_routing_disabled"],
                priority=0,
                estimated_tokens=0
            )
        
        # Batch-level constraints
        max_llm_per_batch = batch_stats.get('max_llm_chunks', float('inf'))
        if llm_chunks_so_far >= max_llm_per_batch:
            return RoutingDecision(
                should_use_llm=False,
                confidence=0.8,
                reasons=["batch_limit_reached"],
                priority=0,
                estimated_tokens=0
            )
        
        # Quality-based routing
        quality_issues = []
        quality_score = 0.0
        
        # Check each quality dimension
        if quality.size_score < 0.7:  # Size issues
            target_words = self.settings.chunking.target_words
            ratio = chunk.word_count / target_words
            if ratio < self.thresholds["too_short_ratio"]:
                quality_issues.append("too_short")
                quality_score += 0.3
            elif ratio > self.thresholds["too_long_ratio"]:
                quality_issues.append("too_long")
                quality_score += 0.2
        
        if quality.boundary_score < 0.6:  # Boundary issues
            quality_issues.append("boundary_problems")
            quality_score += 0.4
        
        if quality.completeness_score < 0.7:  # Completeness issues
            quality_issues.append("incomplete_structures")
            quality_score += 0.3
        
        if quality.boilerplate_score > 0.4:  # High boilerplate likelihood
            quality_issues.append("boilerplate_suspected")
            quality_score += 0.5
        
        if quality.semantic_coherence < 0.6:  # Low coherence
            quality_issues.append("low_coherence")
            quality_score += 0.2
        
        if quality.language_confidence < self.thresholds["language_confidence_min"]:
            quality_issues.append("low_language_confidence")
            quality_score += 0.3
        
        if article_quality < self.thresholds["quality_score_min"]:
            quality_issues.append("low_article_quality")
            quality_score += 0.2
        
        # Additional chunk-specific issues from base chunker
        if chunk.needs_review:
            quality_issues.extend(chunk.review_reasons)
            quality_score += len(chunk.review_reasons) * 0.1
        
        # Decision logic
        if quality_score > 0.5:  # Significant quality issues
            should_use_llm = True
            confidence = min(0.9, quality_score)
            priority = self._calculate_priority(quality_issues, quality)
            reasons.extend(quality_issues)
        
        # Special cases
        if chunk.semantic_type in [SemanticType.LIST, SemanticType.QUOTE]:
            # Lists and quotes are more sensitive to boundary issues
            if "boundary_problems" in quality_issues:
                should_use_llm = True
                priority = max(priority, 3)
                if "list_quote_boundary" not in reasons:
                    reasons.append("list_quote_boundary")
        
        if chunk.importance_score > 0.8:  # Very important chunks
            if quality_score > 0.3:  # Even minor issues in important chunks
                should_use_llm = True
                priority = max(priority, 4)
                if "high_importance" not in reasons:
                    reasons.append("high_importance")
        
        # Cost consideration
        estimated_tokens = self._estimate_token_count(chunk)
        daily_cost_so_far = batch_stats.get('daily_cost_so_far', 0.0)
        estimated_cost = self._estimate_cost(estimated_tokens)
        
        if daily_cost_so_far + estimated_cost > self.settings.rate_limit.daily_cost_limit_usd:
            should_use_llm = False
            confidence = 0.9
            reasons = ["daily_cost_limit"]
            priority = 0
            estimated_tokens = 0
        
        return RoutingDecision(
            should_use_llm=should_use_llm and self.settings.features.llm_chunk_refine_enabled,
            confidence=confidence,
            reasons=reasons,
            priority=priority,
            estimated_tokens=estimated_tokens
        )
    
    def _calculate_size_score(self, size_ratio: float) -> float:
        """Calculate size quality score (1.0 = perfect size)."""
        if 0.8 <= size_ratio <= 1.2:  # Within 20% of target
            return 1.0
        elif 0.6 <= size_ratio <= 1.4:  # Within 40% of target
            return 0.8
        elif 0.4 <= size_ratio <= 1.6:  # Within 60% of target
            return 0.6
        else:
            return 0.3
    
    def _analyze_boundaries(self, chunk: RawChunk) -> float:
        """Analyze how well chunk respects natural boundaries."""
        score = 1.0
        text = chunk.text.strip()
        
        if not text:
            return 0.0
        
        # Check sentence boundaries
        if not self._sentence_beginnings.match(text):
            score -= 0.3  # Doesn't start with capital letter
        
        if not self._sentence_endings.search(text):
            score -= 0.3  # Doesn't end with sentence punctuation
        
        # Check for mid-word breaks
        if self._incomplete_words.search(text):
            score -= 0.4  # Likely truncated word
        
        # Check for mid-sentence breaks
        if self._mid_sentence_indicators.search(text):
            score -= 0.2  # Ends with comma/semicolon (mid-sentence)
        
        # Check list continuation
        if self._list_continuations.match(text):
            score -= 0.3  # Starts with continuation word
        
        return max(0.0, score)
    
    def _analyze_completeness(self, chunk: RawChunk) -> float:
        """Analyze structural completeness of chunk."""
        score = 1.0
        text = chunk.text
        
        # Check for unmatched brackets/quotes
        open_parens = text.count('(')
        close_parens = text.count(')')
        if abs(open_parens - close_parens) > 0:
            score -= 0.2
        
        open_quotes = text.count('"') + text.count('"')
        if open_quotes % 2 != 0:  # Odd number of quotes
            score -= 0.2
        
        # Check for incomplete code blocks
        code_blocks = text.count('```')
        if code_blocks % 2 != 0:  # Unclosed code block
            score -= 0.4
        
        # Check semantic type consistency
        if chunk.semantic_type == SemanticType.LIST:
            # Should have list markers
            list_pattern = re.compile(r'^\s*[-•*]\s+|^\s*\d+\.\s+', re.MULTILINE)
            if not list_pattern.search(text):
                score -= 0.3
        
        elif chunk.semantic_type == SemanticType.QUOTE:
            # Should have quote markers
            if not re.search(r'^>\s+|"[^"]*"', text, re.MULTILINE):
                score -= 0.3
        
        return max(0.0, score)
    
    def _analyze_boilerplate(self, chunk: RawChunk) -> float:
        """Analyze likelihood of chunk being boilerplate."""
        text = chunk.text.lower()
        boilerplate_score = 0.0
        
        # Common boilerplate patterns
        boilerplate_patterns = [
            r'cookie\s+policy',
            r'privacy\s+policy',
            r'terms\s+of\s+service',
            r'subscribe\s+to.*newsletter',
            r'follow\s+us\s+on',
            r'copyright\s+©',
            r'all\s+rights\s+reserved',
            r'share\s+this\s+article',
            r'related\s+articles',
            r'you\s+may\s+also\s+like',
            r'advertisement',
            r'sponsored\s+content',
        ]
        
        for pattern in boilerplate_patterns:
            if re.search(pattern, text):
                boilerplate_score += 0.2
        
        # Repetitive content detection
        words = text.split()
        if len(words) < 50:  # Short chunks more susceptible
            unique_words = set(words)
            repetition_ratio = len(words) / len(unique_words) if unique_words else 1
            if repetition_ratio > 2.0:  # High repetition
                boilerplate_score += 0.3
        
        # Navigation/UI text patterns
        ui_patterns = [
            r'click\s+here',
            r'read\s+more',
            r'continue\s+reading',
            r'next\s+page',
            r'previous\s+page',
            r'menu',
            r'navigation',
            r'search',
        ]
        
        ui_count = sum(1 for pattern in ui_patterns if re.search(pattern, text))
        if ui_count > 2:
            boilerplate_score += 0.4
        
        return min(1.0, boilerplate_score)
    
    def _analyze_semantic_coherence(self, chunk: RawChunk) -> float:
        """Analyze semantic coherence of chunk content."""
        # Simplified coherence analysis
        # In production, this could use more sophisticated NLP
        
        text = chunk.text
        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        if len(sentences) < 2:
            return 0.8  # Single sentence, assume coherent
        
        score = 1.0
        
        # Check for abrupt topic changes (simplified)
        # Look for disconnect indicators
        disconnect_patterns = [
            r'meanwhile',
            r'on\s+the\s+other\s+hand',
            r'however',
            r'but\s+wait',
            r'suddenly',
            r'in\s+other\s+news',
        ]
        
        disconnect_count = 0
        for sentence in sentences:
            for pattern in disconnect_patterns:
                if re.search(pattern, sentence.lower()):
                    disconnect_count += 1
                    break
        
        if disconnect_count > len(sentences) * 0.3:  # >30% disconnected
            score -= 0.4
        
        # Check for consistent terminology/entities
        # Simple heuristic: proper nouns should be consistent
        proper_nouns = re.findall(r'\b[A-Z][a-z]+\b', text)
        if len(proper_nouns) > 10:  # Only for longer chunks
            noun_freq = {}
            for noun in proper_nouns:
                noun_freq[noun] = noun_freq.get(noun, 0) + 1
            
            # If too many single-occurrence nouns, might be incoherent
            singleton_nouns = sum(1 for count in noun_freq.values() if count == 1)
            if singleton_nouns / len(proper_nouns) > 0.8:
                score -= 0.2
        
        return max(0.0, score)
    
    def _get_domain_reputation(self, domain: str) -> float:
        """Get quality reputation score for domain."""
        if domain in self._domain_quality_cache:
            return self._domain_quality_cache[domain]
        
        # Simple domain reputation scoring
        # In production, this would use external reputation data
        
        score = 0.5  # Neutral default
        
        # High-quality domains
        high_quality = {
            'reuters.com': 0.9,
            'bbc.com': 0.9,
            'apnews.com': 0.9,
            'bloomberg.com': 0.85,
            'wsj.com': 0.85,
            'nytimes.com': 0.8,
            'washingtonpost.com': 0.8,
            'theguardian.com': 0.8,
            'cnn.com': 0.75,
            'npr.org': 0.8,
        }
        
        # Low-quality domains
        low_quality = {
            'reddit.com': 0.3,
            'twitter.com': 0.2,
            'facebook.com': 0.2,
            'buzzfeed.com': 0.3,
            'dailymail.co.uk': 0.3,
        }
        
        if domain in high_quality:
            score = high_quality[domain]
        elif domain in low_quality:
            score = low_quality[domain]
        else:
            # Heuristic scoring based on domain characteristics
            if domain.endswith('.edu'):
                score = 0.8  # Educational domains
            elif domain.endswith('.gov'):
                score = 0.9  # Government domains
            elif domain.endswith('.org'):
                score = 0.7  # Organization domains
            elif 'news' in domain or 'times' in domain:
                score = 0.6  # News-related domains
            elif any(tld in domain for tld in ['.co.uk', '.com.au', '.de', '.fr']):
                score = 0.6  # Established country domains
        
        # Cache the result
        self._domain_quality_cache[domain] = score
        return score
    
    def _calculate_priority(self, quality_issues: List[str], quality: QualityIndicators) -> int:
        """Calculate processing priority (1-5, higher = more urgent)."""
        priority = 1
        
        # High-impact issues increase priority
        high_impact_issues = {
            'too_short', 'too_long', 'boilerplate_suspected',
            'incomplete_structures', 'boundary_problems'
        }
        
        impact_count = sum(1 for issue in quality_issues if issue in high_impact_issues)
        priority += min(impact_count, 3)  # Max +3 for multiple high-impact issues
        
        # Domain reputation affects priority
        if quality.domain_reputation > 0.8:
            priority += 1  # High-quality domains get priority
        elif quality.domain_reputation < 0.4:
            priority = max(1, priority - 1)  # Low-quality domains get lower priority
        
        return min(5, priority)
    
    def _estimate_token_count(self, chunk: RawChunk) -> int:
        """Estimate token count for cost calculation."""
        # Rough estimation: 1 token ≈ 4 characters for English
        # Add context tokens for prompt
        chunk_tokens = len(chunk.text) // 4
        context_tokens = 200  # Estimated prompt tokens
        return chunk_tokens + context_tokens
    
    def _estimate_cost(self, token_count: int) -> float:
        """Estimate API cost in USD."""
        input_tokens = int(token_count * 0.8)  # Assume 80% input tokens
        output_tokens = int(token_count * 0.2)  # Assume 20% output tokens
        
        cost = (
            input_tokens * self.settings.rate_limit.cost_per_token_input +
            output_tokens * self.settings.rate_limit.cost_per_token_output
        )
        
        return cost
    
    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        try:
            parsed = urlparse(url)
            return parsed.netloc.lower()
        except Exception:
            return "unknown"
    
    def _analyze_batch_constraints(self, chunks: List[RawChunk], batch_context: Dict) -> Dict:
        """Analyze batch-level constraints for LLM usage."""
        total_chunks = len(chunks)
        max_llm_percentage = self.settings.rate_limit.max_llm_percentage_per_batch
        max_llm_absolute = self.settings.rate_limit.max_llm_calls_per_batch
        
        max_llm_chunks = min(
            int(total_chunks * max_llm_percentage),
            max_llm_absolute
        )
        
        # Get daily cost so far from batch context
        daily_cost_so_far = batch_context.get('daily_cost_so_far', 0.0)
        
        return {
            'max_llm_chunks': max_llm_chunks,
            'daily_cost_so_far': daily_cost_so_far,
            'total_chunks': total_chunks
        }
    
    def get_routing_stats(self, routed_chunks: List[Tuple[RawChunk, RoutingDecision]]) -> Dict:
        """Get routing statistics for monitoring."""
        if not routed_chunks:
            return {}
        
        total_chunks = len(routed_chunks)
        llm_chunks = sum(1 for _, decision in routed_chunks if decision.should_use_llm)
        
        reason_counts = {}
        priority_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        
        total_estimated_tokens = 0
        total_estimated_cost = 0.0
        
        for _, decision in routed_chunks:
            for reason in decision.reasons:
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
            
            priority_counts[decision.priority] = priority_counts.get(decision.priority, 0) + 1
            total_estimated_tokens += decision.estimated_tokens
            total_estimated_cost += self._estimate_cost(decision.estimated_tokens)
        
        return {
            'total_chunks': total_chunks,
            'llm_chunks': llm_chunks,
            'llm_percentage': llm_chunks / total_chunks if total_chunks > 0 else 0,
            'reason_distribution': reason_counts,
            'priority_distribution': priority_counts,
            'estimated_total_tokens': total_estimated_tokens,
            'estimated_total_cost_usd': total_estimated_cost,
            'avg_confidence': sum(d.confidence for _, d in routed_chunks) / total_chunks if total_chunks > 0 else 0
        }
