"""
MMR (Maximal Marginal Relevance) Diversification
Ensures diverse results by balancing relevance and novelty
"""

import numpy as np
import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class DiversificationConfig:
    """Configuration for diversification engine"""
    lambda_param: float = 0.7  # Balance between relevance (1.0) and diversity (0.0)
    max_similarity: float = 0.8  # Maximum similarity between selected items
    domain_diversity_weight: float = 0.3  # Weight for domain diversity
    temporal_diversity_weight: float = 0.2  # Weight for temporal diversity


class MMRDiversifier:
    """Maximal Marginal Relevance diversification engine"""

    def __init__(self, config: Optional[DiversificationConfig] = None):
        self.config = config or DiversificationConfig()

    def calculate_semantic_similarity(self, embedding1: List[float],
                                    embedding2: List[float]) -> float:
        """Calculate cosine similarity between embeddings"""
        if not embedding1 or not embedding2:
            return 0.0

        try:
            # Convert to numpy arrays
            vec1 = np.array(embedding1, dtype=np.float32)
            vec2 = np.array(embedding2, dtype=np.float32)

            # Calculate cosine similarity
            dot_product = np.dot(vec1, vec2)
            norm1 = np.linalg.norm(vec1)
            norm2 = np.linalg.norm(vec2)

            if norm1 == 0 or norm2 == 0:
                return 0.0

            similarity = dot_product / (norm1 * norm2)
            return float(similarity)

        except Exception as e:
            logger.warning(f"Error calculating semantic similarity: {e}")
            return 0.0

    def calculate_domain_similarity(self, domain1: str, domain2: str) -> float:
        """Calculate domain-based similarity"""
        if not domain1 or not domain2:
            return 0.0

        # Exact match
        if domain1.lower() == domain2.lower():
            return 1.0

        # Same parent domain (e.g., sports.cnn.com vs cnn.com)
        d1_parts = domain1.lower().split('.')
        d2_parts = domain2.lower().split('.')

        # Check if one is subdomain of another
        if len(d1_parts) >= 2 and len(d2_parts) >= 2:
            d1_base = '.'.join(d1_parts[-2:])
            d2_base = '.'.join(d2_parts[-2:])
            if d1_base == d2_base:
                return 0.8

        return 0.0

    def calculate_temporal_similarity(self, time1: datetime, time2: datetime) -> float:
        """Calculate temporal similarity (closer in time = more similar)"""
        if not time1 or not time2:
            return 0.0

        try:
            # Handle timezone-naive datetimes
            if time1.tzinfo is None:
                time1 = time1.replace(tzinfo=None)
            if time2.tzinfo is None:
                time2 = time2.replace(tzinfo=None)

            # Calculate time difference in hours
            time_diff_hours = abs((time1 - time2).total_seconds() / 3600)

            # Exponential decay: similar times get higher similarity
            # 1 hour = 0.9, 6 hours = 0.5, 24 hours = 0.1
            similarity = np.exp(-time_diff_hours / 12)
            return float(similarity)

        except Exception as e:
            logger.warning(f"Error calculating temporal similarity: {e}")
            return 0.0

    def calculate_content_similarity(self, result1: Dict[str, Any],
                                   result2: Dict[str, Any]) -> float:
        """Calculate overall content similarity between two results"""
        similarities = []

        # Semantic similarity (if embeddings available)
        emb1 = result1.get('embedding')
        emb2 = result2.get('embedding')
        if emb1 and emb2:
            sem_sim = self.calculate_semantic_similarity(emb1, emb2)
            similarities.append(sem_sim)

        # Domain similarity
        domain1 = result1.get('source_domain', result1.get('domain', result1.get('source', '')))
        domain2 = result2.get('source_domain', result2.get('domain', result2.get('source', '')))
        domain_sim = self.calculate_domain_similarity(domain1, domain2)
        similarities.append(domain_sim * self.config.domain_diversity_weight)

        # Temporal similarity
        time1 = result1.get('published_at')
        time2 = result2.get('published_at')

        if isinstance(time1, str):
            try:
                time1 = datetime.fromisoformat(time1.replace('Z', '+00:00'))
            except:
                time1 = None

        if isinstance(time2, str):
            try:
                time2 = datetime.fromisoformat(time2.replace('Z', '+00:00'))
            except:
                time2 = None

        if time1 and time2:
            temp_sim = self.calculate_temporal_similarity(time1, time2)
            similarities.append(temp_sim * self.config.temporal_diversity_weight)

        # Return maximum similarity (most restrictive)
        return max(similarities) if similarities else 0.0

    def mmr_diversify(self, results: List[Dict[str, Any]],
                     max_results: int = 10) -> List[Dict[str, Any]]:
        """Apply MMR diversification to search results"""
        if not results or len(results) <= max_results:
            return results

        if max_results <= 0:
            return []

        selected = []
        candidates = results.copy()

        # Select first item (highest relevance)
        if candidates:
            first_item = candidates.pop(0)
            selected.append(first_item)

        # Select remaining items using MMR
        while len(selected) < max_results and candidates:
            best_score = -float('inf')
            best_idx = -1

            for i, candidate in enumerate(candidates):
                # Relevance score (normalized final score)
                relevance = candidate.get('scores', {}).get('final', 0.0)

                # Calculate max similarity to already selected items
                max_similarity = 0.0
                for selected_item in selected:
                    similarity = self.calculate_content_similarity(candidate, selected_item)
                    max_similarity = max(max_similarity, similarity)

                # MMR score: λ * relevance - (1-λ) * max_similarity
                mmr_score = (self.config.lambda_param * relevance -
                           (1 - self.config.lambda_param) * max_similarity)

                if mmr_score > best_score:
                    best_score = mmr_score
                    best_idx = i

            # Add best candidate to selected
            if best_idx >= 0:
                selected_item = candidates.pop(best_idx)
                selected_item['mmr_score'] = best_score
                selected.append(selected_item)

        logger.info(f"MMR diversification: {len(results)} -> {len(selected)} results")
        return selected

    def ensure_domain_diversity(self, results: List[Dict[str, Any]],
                               max_per_domain: int = 3) -> List[Dict[str, Any]]:
        """Ensure no domain dominates the results"""
        if not results:
            return results

        domain_counts = {}
        diverse_results = []

        for result in results:
            domain = result.get('source_domain', result.get('domain', result.get('source', 'unknown')))
            current_count = domain_counts.get(domain, 0)

            if current_count < max_per_domain:
                diverse_results.append(result)
                domain_counts[domain] = current_count + 1
            else:
                # Mark as filtered for domain diversity
                result['filtered_reason'] = 'domain_diversity'

        logger.info(f"Domain diversity filter: {len(results)} -> {len(diverse_results)} results")
        return diverse_results

    def ensure_temporal_diversity(self, results: List[Dict[str, Any]],
                                 min_time_gap_hours: int = 2) -> List[Dict[str, Any]]:
        """Ensure temporal diversity in results"""
        if not results or len(results) <= 1:
            return results

        diverse_results = []
        last_times = []

        for result in results:
            published_at = result.get('published_at')
            if not published_at:
                diverse_results.append(result)
                continue

            try:
                if isinstance(published_at, str):
                    pub_time = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
                else:
                    pub_time = published_at

                # Check if this time is sufficiently different from previous times
                is_diverse = True
                for last_time in last_times:
                    time_diff_hours = abs((pub_time - last_time).total_seconds() / 3600)
                    if time_diff_hours < min_time_gap_hours:
                        is_diverse = False
                        break

                if is_diverse:
                    diverse_results.append(result)
                    last_times.append(pub_time)
                else:
                    result['filtered_reason'] = 'temporal_diversity'

            except Exception as e:
                logger.warning(f"Error processing timestamp for temporal diversity: {e}")
                diverse_results.append(result)

        logger.info(f"Temporal diversity filter: {len(results)} -> {len(diverse_results)} results")
        return diverse_results

    def diversify_results(self, results: List[Dict[str, Any]],
                         max_results: int = 10,
                         ensure_domain_div: bool = True,
                         ensure_temporal_div: bool = False) -> List[Dict[str, Any]]:
        """Complete diversification pipeline"""
        if not results:
            return results

        logger.info(f"Starting diversification pipeline with {len(results)} results")

        # Step 1: Apply MMR diversification
        mmr_results = self.mmr_diversify(results, max_results * 2)  # Get more candidates

        # Step 2: Ensure domain diversity
        if ensure_domain_div:
            diverse_results = self.ensure_domain_diversity(mmr_results)
        else:
            diverse_results = mmr_results

        # Step 3: Ensure temporal diversity (optional)
        if ensure_temporal_div:
            diverse_results = self.ensure_temporal_diversity(diverse_results)

        # Step 4: Trim to final size
        final_results = diverse_results[:max_results]

        logger.info(f"Diversification complete: {len(results)} -> {len(final_results)} results")
        return final_results

    def analyze_diversity(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze diversity metrics of result set"""
        if not results:
            return {}

        # Domain diversity
        domains = [r.get('source_domain', r.get('domain', r.get('source', 'unknown'))) for r in results]
        unique_domains = len(set(domains))
        domain_distribution = {}
        for domain in domains:
            domain_distribution[domain] = domain_distribution.get(domain, 0) + 1

        # Temporal spread
        timestamps = []
        for result in results:
            published_at = result.get('published_at')
            if published_at:
                try:
                    if isinstance(published_at, str):
                        timestamp = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
                    else:
                        timestamp = published_at
                    timestamps.append(timestamp)
                except:
                    continue

        temporal_span_hours = 0
        if len(timestamps) > 1:
            timestamps.sort()
            temporal_span_hours = (timestamps[-1] - timestamps[0]).total_seconds() / 3600

        # Content similarity analysis
        similarities = []
        if len(results) > 1:
            for i in range(len(results)):
                for j in range(i + 1, len(results)):
                    sim = self.calculate_content_similarity(results[i], results[j])
                    similarities.append(sim)

        avg_similarity = np.mean(similarities) if similarities else 0.0
        max_similarity = max(similarities) if similarities else 0.0

        return {
            'total_results': len(results),
            'unique_domains': unique_domains,
            'domain_diversity_ratio': unique_domains / len(results) if results else 0,
            'domain_distribution': domain_distribution,
            'temporal_span_hours': temporal_span_hours,
            'avg_content_similarity': round(avg_similarity, 3),
            'max_content_similarity': round(max_similarity, 3),
            'diversity_score': round(1 - avg_similarity, 3)  # Higher is more diverse
        }