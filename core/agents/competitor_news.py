"""
CompetitorNews Agent — Phase 2: Analyze domain/topic overlap, positioning, sentiment deltas
Primary: claude-4.5, Fallback: gpt-5, QC: gemini-2.5-pro
"""

import logging
import json
from typing import List, Dict, Any, Optional, Set, Tuple
from collections import Counter, defaultdict
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


COMPETITOR_SYSTEM_PROMPT = """You are a competitive intelligence analyst specialized in news coverage analysis.

TASK: Analyze competitive landscape across news domains/sources, identifying overlap, gaps, and positioning.

INPUT:
- List of domains/sources to compare
- News articles with domain, topics, sentiment

OUTPUT FORMAT (strict JSON):
{
  "overlap_matrix": [
    { "domain": "domain.com", "topic": "topic name", "overlap_score": 0.85 }
  ],
  "gaps": ["topic1", "topic2"],
  "positioning": [
    { "domain": "domain.com", "stance": "leader|fast_follower|niche", "notes": "brief explanation" }
  ],
  "sentiment_delta": [
    { "domain": "domain.com", "delta": 0.3 }
  ],
  "top_domains": ["domain1.com", "domain2.com", ...]
}

RULES:
1. overlap_score: 0-1, measures topic coverage similarity between domains
2. gaps: topics covered by competitors but missing from focal domain
3. stance: "leader" = high coverage + authority, "fast_follower" = reactive, "niche" = specialized
4. sentiment_delta: relative sentiment compared to baseline (positive = more positive coverage)
5. top_domains: ranked by article count or relevance
6. Return ONLY valid JSON, no additional text
"""


def extract_domain(url: str) -> Optional[str]:
    """Extract clean domain from URL"""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
    except Exception:
        return None


def compute_jaccard_similarity(set1: Set[str], set2: Set[str]) -> float:
    """Compute Jaccard similarity between two sets"""
    if not set1 and not set2:
        return 0.0
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    return intersection / union if union > 0 else 0.0


def classify_stance(
    domain: str,
    domain_article_count: int,
    total_articles: int,
    topic_diversity: int
) -> str:
    """
    Classify competitive stance

    Args:
        domain: Domain name
        domain_article_count: Number of articles from this domain
        total_articles: Total articles in dataset
        topic_diversity: Number of unique topics covered by domain

    Returns:
        "leader", "fast_follower", or "niche"
    """
    coverage_ratio = domain_article_count / total_articles if total_articles > 0 else 0

    if coverage_ratio > 0.2 and topic_diversity > 5:
        return "leader"
    elif coverage_ratio > 0.1 and topic_diversity > 3:
        return "fast_follower"
    else:
        return "niche"


async def run_competitor_news(
    docs: List[Dict[str, Any]],
    domains: Optional[List[str]],
    niche: Optional[str],
    correlation_id: str
) -> Dict[str, Any]:
    """
    Execute competitor news analysis

    Args:
        docs: Retrieved articles with url/domain/title/snippet
        domains: List of specific domains to analyze (optional)
        niche: Niche/topic for semantic domain discovery (optional)
        correlation_id: Correlation ID for telemetry

    Returns:
        CompetitorsResult dict
    """
    logger.info(
        f"[{correlation_id}] CompetitorNews: domains={domains}, niche={niche}, docs={len(docs)}"
    )

    try:
        # Extract domains from docs
        domain_docs = defaultdict(list)
        domain_counts = Counter()

        for doc in docs:
            url = doc.get("url", "")
            domain = extract_domain(url)

            if domain:
                domain_docs[domain].append(doc)
                domain_counts[domain] += 1

        # Filter domains
        if domains:
            # Use specified domains
            target_domains = [d.lower() for d in domains]
            domain_docs = {d: domain_docs[d] for d in target_domains if d in domain_docs}
        else:
            # Auto-detect top domains (frequency threshold ≥ 3)
            target_domains = [d for d, count in domain_counts.items() if count >= 3]

        if not target_domains:
            logger.warning(f"[{correlation_id}] No domains found with sufficient coverage")
            target_domains = list(domain_counts.keys())[:5]  # Fallback to top 5

        logger.info(f"[{correlation_id}] Analyzing {len(target_domains)} domains")

        # Build topic sets per domain (simple keyword extraction)
        domain_topics = {}
        for domain in target_domains:
            topics = set()
            for doc in domain_docs[domain]:
                title = doc.get("title", "").lower()
                snippet = doc.get("snippet", "").lower()
                text = f"{title} {snippet}"

                # Extract keywords (simple approach)
                words = text.split()
                # Filter common words
                keywords = [w for w in words if len(w) > 4 and w.isalpha()]
                topics.update(keywords[:10])  # Top 10 keywords per doc

            domain_topics[domain] = topics

        # Compute overlap matrix
        overlap_matrix = []
        all_topics = set()
        for domain in target_domains:
            all_topics.update(domain_topics[domain])

        # Compute pairwise overlaps
        for i, domain1 in enumerate(target_domains):
            for j, domain2 in enumerate(target_domains):
                if i < j:  # Avoid duplicates
                    similarity = compute_jaccard_similarity(
                        domain_topics[domain1],
                        domain_topics[domain2]
                    )

                    # Find common topics
                    common_topics = domain_topics[domain1] & domain_topics[domain2]
                    for topic in list(common_topics)[:3]:  # Top 3 common topics
                        overlap_matrix.append({
                            "domain": f"{domain1} vs {domain2}",
                            "topic": topic,
                            "overlap_score": similarity
                        })

        # Identify gaps (topics covered by others but not by focal domain)
        if target_domains:
            focal_domain = target_domains[0]  # Assume first is focal
            focal_topics = domain_topics[focal_domain]

            gaps = []
            for domain in target_domains[1:]:
                competitor_topics = domain_topics[domain]
                gap_topics = competitor_topics - focal_topics
                gaps.extend(list(gap_topics)[:2])  # Top 2 gaps per competitor

            gaps = list(set(gaps))[:5]  # Max 5 unique gaps
        else:
            gaps = []

        # Classify positioning
        positioning = []
        total_articles = len(docs)
        for domain in target_domains:
            article_count = domain_counts[domain]
            topic_diversity = len(domain_topics[domain])

            stance = classify_stance(domain, article_count, total_articles, topic_diversity)

            positioning.append({
                "domain": domain,
                "stance": stance,
                "notes": f"{article_count} articles, {topic_diversity} topics"
            })

        # Compute sentiment deltas (simple: based on article count as proxy)
        # In production, would use actual sentiment scores
        sentiment_delta = []
        avg_coverage = sum(domain_counts.values()) / len(domain_counts) if domain_counts else 1

        for domain in target_domains:
            count = domain_counts[domain]
            delta = (count - avg_coverage) / avg_coverage if avg_coverage > 0 else 0.0
            delta = max(-2.0, min(2.0, delta))  # Clamp to [-2, 2]

            sentiment_delta.append({
                "domain": domain,
                "delta": delta
            })

        # Top domains by article count
        top_domains = [d for d, _ in domain_counts.most_common(10)]

        result = {
            "overlap_matrix": overlap_matrix[:20],  # Max 20
            "gaps": gaps,
            "positioning": positioning[:10],  # Max 10
            "sentiment_delta": sentiment_delta[:10],  # Max 10
            "top_domains": top_domains,
            "success": True
        }

        logger.info(
            f"[{correlation_id}] CompetitorNews completed: {len(positioning)} domains, {len(gaps)} gaps"
        )

        return result

    except Exception as e:
        logger.error(f"[{correlation_id}] CompetitorNews failed: {e}", exc_info=True)
        return {
            "overlap_matrix": [],
            "gaps": [],
            "positioning": [],
            "sentiment_delta": [],
            "top_domains": [],
            "success": False,
            "error": str(e)
        }
