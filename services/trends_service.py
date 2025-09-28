"""
TrendsService: builds production-grade /trends payload using embeddings + clustering + keywording + simple dynamics.

Design goals:
- No heavy optional deps (HDBSCAN/KeyBERT); rely on sklearn + our LocalEmbeddingGenerator
- Provide interpretable labels via TF-IDF over cluster texts (c-TF-IDF inspired)
- Basic dynamics: hour buckets, momentum, simple burst heuristic
- Cache results for a short TTL to keep /trends fast at runtime
"""

from __future__ import annotations

import math
import time
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sklearn.cluster import DBSCAN
from sklearn.feature_extraction.text import TfidfVectorizer
import numpy as np

from database.production_db_client import ProductionDBClient
from local_embedding_generator import LocalEmbeddingGenerator


logger = logging.getLogger(__name__)


@dataclass
class TrendTopic:
    label: str
    count: int
    momentum: float
    burst: Dict[str, Any]
    top_keywords: List[str]
    top_articles: List[Dict[str, Any]]
    score: float


class TrendsService:
    def __init__(self, db: ProductionDBClient, *, cache_ttl_seconds: int = 600) -> None:
        self.db = db
        # Optional fallback generator; main path uses embeddings from DB (pgvector/JSON)
        self.embedder = LocalEmbeddingGenerator()
        self._cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
        self.cache_ttl = cache_ttl_seconds

    def _cache_get(self, key: str) -> Optional[Dict[str, Any]]:
        item = self._cache.get(key)
        if not item:
            return None
        ts, value = item
        if (time.time() - ts) < self.cache_ttl:
            return value
        self._cache.pop(key, None)
        return None

    def _cache_set(self, key: str, value: Dict[str, Any]) -> None:
        self._cache[key] = (time.time(), value)

    # ----------------------- Data fetch -----------------------
    def _fetch_articles_with_embeddings(self, hours: int, limit: int) -> List[Dict[str, Any]]:
        """Fetch recent canonical articles with one representative chunk embedding each."""
        try:
            with self.db._cursor() as cur:
                cur.execute(
                    """
                    SELECT ai.article_id, ai.url, ai.source, ai.domain,
                           ai.title_norm, ai.clean_text, ai.published_at,
                           ac.embedding
                    FROM articles_index ai
                    JOIN LATERAL (
                        SELECT ac.embedding
                        FROM article_chunks ac
                        WHERE ac.article_id = ai.article_id AND ac.embedding IS NOT NULL
                        ORDER BY ac.chunk_index ASC
                        LIMIT 1
                    ) ac ON TRUE
                    WHERE ai.published_at >= NOW() - (%s || ' hours')::interval
                      AND (ai.is_canonical IS TRUE OR ai.is_canonical IS NULL)
                    ORDER BY ai.published_at DESC NULLS LAST
                    LIMIT %s
                    """,
                    (int(hours), limit),
                )
                cols = [d[0] for d in cur.description]
                return [dict(zip(cols, r)) for r in cur.fetchall()]
        except Exception as e:
            logger.error(f"Failed to fetch articles with embeddings: {e}")
            return []

    # ----------------------- Embeddings -----------------------
    def _prepare_texts(self, articles: List[Dict[str, Any]]) -> List[str]:
        texts: List[str] = []
        for a in articles:
            title = (a.get("title_norm") or "").strip()
            body = (a.get("clean_text") or "").strip()
            if body:
                body = body.split("\n")[0][:280]
            text = (title + ". " + body).strip()
            texts.append(text or title or "")
        return texts

    # ----------------------- Clustering -----------------------
    def _cluster(self, embeddings: List[Optional[List[float]]]) -> np.ndarray:
        X = np.array([e for e in embeddings if e is not None], dtype=float)
        if X.size == 0:
            return np.array([])
        # Map back to original indices (some embeddings may be None)
        valid_idx = [i for i, e in enumerate(embeddings) if e is not None]
        # DBSCAN with cosine distance is a reasonable default without HDBSCAN
        db = DBSCAN(eps=0.30, min_samples=5, metric="cosine")
        labels = db.fit_predict(X)
        # Build full label array aligned with input
        full = -np.ones(len(embeddings), dtype=int)
        for j, li in enumerate(labels):
            full[valid_idx[j]] = int(li)
        return full

    # ----------------------- Labeling via c-TF-IDF-like -----------------------
    def _label_clusters(
        self, texts: List[str], labels: np.ndarray, topk: int = 6
    ) -> Dict[int, List[str]]:
        cluster_ids = sorted({int(l) for l in labels if l >= 0})
        if not cluster_ids:
            return {}
        # Create corpus per cluster by concatenating cluster docs
        cluster_docs: List[str] = []
        id_map: List[int] = []
        for cid in cluster_ids:
            joined = "\n".join([texts[i] for i, l in enumerate(labels) if l == cid])
            cluster_docs.append(joined)
            id_map.append(cid)
        # TF-IDF over cluster documents approximates c-TF-IDF
        vec = TfidfVectorizer(max_features=5000, ngram_range=(1, 2), stop_words="english")
        M = vec.fit_transform(cluster_docs)  # shape: [clusters, vocab]
        feature_names = np.array(vec.get_feature_names_out())
        top_per_cluster: Dict[int, List[str]] = {}
        for ridx, cid in enumerate(id_map):
            row = M.getrow(ridx)
            if row.nnz == 0:
                top_per_cluster[cid] = []
                continue
            data = row.toarray().ravel()
            idxs = np.argsort(-data)[:topk]
            top_per_cluster[cid] = [t for t in feature_names[idxs] if t.strip()]
        return top_per_cluster

    # ----------------------- Dynamics -----------------------
    def _hour_buckets(self, datetimes: List[datetime], hours: int) -> List[int]:
        if not datetimes:
            return [0] * hours
        now = datetime.utcnow()
        # buckets: hours ago  (oldest first)
        counts = [0] * hours
        for dt in datetimes:
            delta = now - dt
            h = int(delta.total_seconds() // 3600)
            if 0 <= h < hours:
                # reverse index to build chronological vector oldest->newest
                idx = hours - 1 - h
                counts[idx] += 1
        return counts

    def _momentum_and_burst(self, series: List[int]) -> Tuple[float, Dict[str, Any]]:
        n = len(series)
        if n < 4:
            return 0.0, {"active": False, "level": 0}
        half = n // 2
        left = series[:half]
        right = series[half:]
        left_sum = max(1, sum(left))
        right_sum = sum(right)
        momentum = (right_sum - left_sum) / left_sum
        # Simple burst heuristic on last 3 points vs history
        mu = np.mean(series[:-3]) if n > 3 else np.mean(series)
        sigma = np.std(series[:-3]) if n > 3 else (np.std(series) or 1.0)
        recent = series[-1]
        z = (recent - mu) / (sigma if sigma > 0 else 1.0)
        if z >= 3:
            burst = {"active": True, "level": 2}
        elif z >= 2:
            burst = {"active": True, "level": 1}
        else:
            burst = {"active": False, "level": 0}
        return float(momentum), burst

    # ----------------------- Ranking -----------------------
    def _rank(self, topics: List[TrendTopic]) -> List[TrendTopic]:
        # Normalize counts
        max_cnt = max((t.count for t in topics), default=1)
        for t in topics:
            volume = t.count / max_cnt if max_cnt else 0.0
            burst_intensity = {0: 0.0, 1: 0.6, 2: 1.0}.get(t.burst.get("level", 0), 0.0)
            t.score = 0.5 * burst_intensity + 0.3 * max(min(t.momentum, 3.0), -1.0) + 0.2 * volume
        return sorted(topics, key=lambda x: x.score, reverse=True)

    # ----------------------- Public API -----------------------
    def build_trends(self, window: str = "24h", limit: int = 600, topn: int = 10) -> Dict[str, Any]:
        cache_key = f"trends:{window}:{limit}:{topn}"
        cached = self._cache_get(cache_key)
        if cached:
            return cached

        # Parse window hours
        if window.endswith("h"):
            hours = int(window[:-1])
        elif window.endswith("d"):
            hours = int(window[:-1]) * 24
        else:
            hours = 24

        # Fetch articles paired with an embedding from DB
        rows = self._fetch_articles_with_embeddings(hours, limit)
        if not rows:
            payload = {"status": "ok", "data": [], "errors": ["no_data"]}
            self._cache_set(cache_key, payload)
            return payload

        # Prepare texts and parse embeddings
        texts: List[str] = []
        embs: List[Optional[List[float]]] = []
        def _parse_embedding(val: Any) -> Optional[List[float]]:
            try:
                if val is None:
                    return None
                if isinstance(val, list):
                    return [float(x) for x in val]
                if isinstance(val, (bytes, bytearray, memoryview)):
                    s = bytes(val).decode('utf-8', errors='ignore')
                else:
                    s = str(val)
                s = s.strip()
                if s.startswith('[') and s.endswith(']'):
                    import json as _json
                    return [float(x) for x in _json.loads(s)]
                # Fallback: split by comma
                if ',' in s:
                    return [float(x.strip()) for x in s.strip('[]').split(',')]
            except Exception:
                return None
            return None

        for r in rows:
            texts.append(self._prepare_texts([r])[0])
            embs.append(_parse_embedding(r.get('embedding')))

        labels = self._cluster(embs)
        if labels.size == 0:
            payload = {"status": "ok", "data": [], "errors": ["no_embeddings"]}
            self._cache_set(cache_key, payload)
            return payload

        # Build topics from clusters
        label_to_indices: Dict[int, List[int]] = {}
        for i, l in enumerate(labels):
            if l < 0:
                continue
            label_to_indices.setdefault(int(l), []).append(i)

        # Generate labels (keywords) per cluster
        cluster_keywords = self._label_clusters(texts, labels, topk=6)

        topics: List[TrendTopic] = []
        for cid, idxs in label_to_indices.items():
            dt_list = [rows[i]["published_at"] for i in idxs if rows[i].get("published_at")]
            series = self._hour_buckets(dt_list, min(hours, 48))
            momentum, burst = self._momentum_and_burst(series)
            # pick showcase articles (top 3 most recent)
            showcase = sorted(
                (rows[i] for i in idxs), key=lambda a: a.get("published_at") or datetime.min, reverse=True
            )[:3]
            top_articles = [
                {"title": (a.get("title_norm") or "").strip()[:140], "source": a.get("domain") or a.get("source"), "url": a.get("url")}
                for a in showcase
            ]
            kws = cluster_keywords.get(cid, [])
            label_txt = ", ".join(kws[:2]) if kws else "General"
            topics.append(
                TrendTopic(
                    label=label_txt,
                    count=len(idxs),
                    momentum=round(float(momentum), 3),
                    burst=burst,
                    top_keywords=kws[:8],
                    top_articles=top_articles,
                    score=0.0,
                )
            )

        ranked = self._rank(topics)
        # Build payload
        data = [
            {
                "label": t.label,
                "count": t.count,
                "momentum": t.momentum,
                "burst": t.burst,
                "top_keywords": t.top_keywords,
                "top_articles": t.top_articles,
            }
            for t in ranked[:topn]
        ]

        payload = {"status": "ok", "data": data, "errors": []}
        self._cache_set(cache_key, payload)
        return payload

    def format_trends_markdown(self, payload: Dict[str, Any], window: str = "24h") -> str:
        if payload.get("status") != "ok" or not payload.get("data"):
            return "📭 Тренды не найдены за выбранный период"
        lines = [f"📈 Тренды за {window}"]
        for i, t in enumerate(payload["data"], start=1):
            burst = t.get("burst", {})
            burst_emoji = "🚨" if burst.get("active") else ""  # simple indicator
            label = t.get("label") or "General"
            count = t.get("count", 0)
            momentum = t.get("momentum", 0.0)
            kws = ", ".join(t.get("top_keywords", [])[:6])
            lines.append(f"\n{i}. {burst_emoji} **{label}** — {count} шт, Δ {momentum:+.0%}")
            if kws:
                lines.append(f"   🔑 {kws}")
            # Articles
            arts = t.get("top_articles", [])
            for a in arts[:3]:
                tt = (a.get("title") or "").replace("\n", " ")
                src = a.get("source") or ""
                url = a.get("url") or ""
                # Use plain URL to avoid parse issues in Markdown
                if url:
                    lines.append(f"   • {tt} ({src})\n     {url}")
                else:
                    lines.append(f"   • {tt} ({src})")
        return "\n".join(lines)
