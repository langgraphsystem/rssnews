"""
Search API for GPT Actions
FastAPI endpoint that provides /retrieve for OpenAI SearchAgent

Architecture:
- POST /retrieve: Main search endpoint with pagination
- GET /health: Health check endpoint
- Cursor-based pagination for stateless iteration
- Auto-retry logic support (24h → 48h → 72h)
"""

import os
import sys
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import base64
import json

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from enum import Enum

# Import existing services
from ranking_api import RankingAPI, SearchRequest

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI(
    title="RSS News Search API",
    description="Search API for OpenAI GPT Actions",
    version="1.0.0"
)

# Global instances
pg_client = None  # Kept for backward-compatible health reporting
ranking_api: Optional[RankingAPI] = None


# ============================================================================
# Pydantic Models (Request/Response)
# ============================================================================

class RetrieveRequest(BaseModel):
    """Request model for /retrieve endpoint"""
    query: str = Field(..., description="Search query")
    hours: int = Field(24, description="Time window in hours (24, 48, or 72)")
    k: int = Field(10, description="Number of results to return")
    filters: Dict[str, Any] = Field(default_factory=dict, description="Optional filters")
    cursor: Optional[str] = Field(None, description="Pagination cursor (base64-encoded offset)")
    correlation_id: Optional[str] = Field(None, description="Request correlation ID for tracking")


class ArticleItem(BaseModel):
    """Single article result"""
    title: str
    url: str
    source_domain: str
    published_at: str  # ISO 8601 format
    snippet: Optional[str] = None
    relevance_score: Optional[float] = None


class RetrieveResponse(BaseModel):
    """Response model for /retrieve endpoint"""
    items: List[ArticleItem]
    next_cursor: Optional[str] = Field(None, description="Cursor for next page (null if no more results)")
    total_available: int = Field(..., description="Total results available in this time window")
    coverage: float = Field(..., description="Coverage metric (0.0-1.0)")
    freshness_stats: Dict[str, Any] = Field(default_factory=dict, description="Freshness metrics")
    diagnostics: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Debug information")


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    database: str
    ranking_api: str
    timestamp: str


class ErrorCode(str, Enum):
    """Error codes for API responses"""
    NO_RESULTS = "NO_RESULTS"
    RATE_LIMIT = "RATE_LIMIT"
    INVALID_PARAMS = "INVALID_PARAMS"
    DATABASE_ERROR = "DATABASE_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


# ============================================================================
# Startup/Shutdown Events
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize database and ranking API connections"""
    global pg_client, ranking_api

    logger.info("🚀 Starting Search API...")

    try:
        # Initialize RankingAPI (manages its own DB client internally)
        ranking_api = RankingAPI()
        logger.info("✅ RankingAPI initialized")

        logger.info("🎉 Search API ready")

    except Exception as e:
        logger.error(f"❌ Startup failed: {e}")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup connections"""
    global pg_client

    logger.info("🛑 Shutting down Search API...")

    if pg_client:
        await pg_client.close()
        logger.info("✅ PostgreSQL connection closed")


# ============================================================================
# Helper Functions
# ============================================================================

def _encode_cursor(offset: int) -> str:
    """Encode offset as base64 cursor"""
    cursor_data = {"offset": offset}
    cursor_json = json.dumps(cursor_data)
    cursor_b64 = base64.b64encode(cursor_json.encode()).decode()
    return cursor_b64


def _decode_cursor(cursor: str) -> int:
    """Decode base64 cursor to offset"""
    try:
        cursor_json = base64.b64decode(cursor.encode()).decode()
        cursor_data = json.loads(cursor_json)
        return cursor_data.get("offset", 0)
    except Exception as e:
        logger.warning(f"Failed to decode cursor: {e}")
        return 0


def _hours_to_window(hours: int) -> str:
    """Convert hours to time window string"""
    if hours <= 24:
        return "24h"
    elif hours <= 48:
        return "48h"
    elif hours <= 72:
        return "72h"
    else:
        return "72h"  # Max window


def _calculate_freshness_median(results: List[Dict[str, Any]]) -> float:
    """Calculate median freshness in seconds"""
    if not results:
        return 0.0

    now = datetime.utcnow()
    freshness_values = []

    for result in results:
        published_at = result.get("published_at")
        if published_at:
            try:
                if isinstance(published_at, str):
                    pub_time = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
                else:
                    pub_time = published_at

                # Remove timezone for comparison
                if pub_time.tzinfo is not None:
                    pub_time = pub_time.replace(tzinfo=None)

                age_seconds = (now - pub_time).total_seconds()
                freshness_values.append(age_seconds)
            except:
                continue

    if not freshness_values:
        return 0.0

    freshness_values.sort()
    mid = len(freshness_values) // 2

    if len(freshness_values) % 2 == 0:
        median = (freshness_values[mid - 1] + freshness_values[mid]) / 2
    else:
        median = freshness_values[mid]

    return round(median, 2)


def _format_article_item(article: Dict[str, Any]) -> ArticleItem:
    """Convert article dict to ArticleItem model"""
    # Handle published_at format
    published_at = article.get("published_at", "")
    if isinstance(published_at, datetime):
        published_at = published_at.isoformat()

    return ArticleItem(
        title=article.get("title", "Untitled"),
        url=article.get("url", article.get("link", "")),
        source_domain=article.get("source_domain", article.get("domain", article.get("source", "unknown"))),
        published_at=published_at,
        snippet=article.get("snippet", article.get("summary", ""))[:300] if article.get("snippet") or article.get("summary") else None,
        relevance_score=article.get("scores", {}).get("final", article.get("score"))
    )


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/", response_class=JSONResponse)
async def root():
    """Root endpoint - API information"""
    return {
        "name": "RSS News Search API",
        "version": "1.0.0",
        "endpoints": {
            "retrieve": "POST /retrieve",
            "health": "GET /health"
        },
        "documentation": "/docs"
    }


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    global pg_client, ranking_api

    db_status = "disconnected"
    api_status = "not_initialized"

    # Check database connection
    if pg_client:
        try:
            # Simple query to test connection
            await pg_client.execute("SELECT 1")
            db_status = "connected"
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            db_status = f"error: {str(e)[:50]}"

    # Check ranking API
    if ranking_api:
        api_status = "ready"

    overall_status = "healthy" if db_status == "connected" and api_status == "ready" else "unhealthy"

    return HealthResponse(
        status=overall_status,
        database=db_status,
        ranking_api=api_status,
        timestamp=datetime.utcnow().isoformat()
    )


@app.post("/retrieve", response_model=RetrieveResponse)
async def retrieve(
    request: RetrieveRequest,
    x_request_id: Optional[str] = Header(default=None, alias="X-Request-Id"),
    openai_request_id: Optional[str] = Header(default=None, alias="OpenAI-Request-ID"),
):
    """
    Main search endpoint for GPT Actions

    Supports:
    - Cursor-based pagination
    - Auto-retry logic (caller should retry with hours=48, then 72)
    - Coverage and freshness metrics
    """
    global ranking_api

    if not ranking_api:
        raise HTTPException(status_code=503, detail="RankingAPI not initialized")

    try:
        # Decode cursor to get offset
        offset = 0
        if request.cursor:
            offset = _decode_cursor(request.cursor)

        # Convert hours to window
        window = _hours_to_window(request.hours)

        # Log request (safe)
        req_id = x_request_id or openai_request_id
        q_preview = (request.query or "")[:120].replace("\n", " ")
        try:
            filt_keys = list((request.filters or {}).keys())
        except Exception:
            filt_keys = []
        logger.info(
            "[AB]/retrieve start | req_id=%s corr=%s hours=%s k=%s offset=%s filters=%s q='%s'",
            req_id,
            request.correlation_id,
            request.hours,
            request.k,
            offset,
            filt_keys,
            q_preview,
        )

        # Call RankingAPI's retrieve_for_analysis method
        # We need to fetch k + offset results, then slice
        k_total = request.k + offset

        try:
            # Map filters to RankingAPI params
            filt = request.filters or {}
            sources = filt.get("sources") if isinstance(filt, dict) else None
            lang = filt.get("lang") if isinstance(filt, dict) else None

            res = await ranking_api.retrieve_for_analysis(
                query=request.query,
                window=window,
                k_final=k_total,
                intent="news_current_events",
                sources=sources,
                lang=lang or "auto",
                correlation_id=request.correlation_id,
            )
        except Exception as e:
            logger.error(f"RankingAPI retrieve_for_analysis failed: {e}")
            raise HTTPException(
                status_code=500,
                detail={"error_code": ErrorCode.DATABASE_ERROR, "message": str(e)}
            )

        # Extract docs from response and slice for pagination
        all_docs = []
        if isinstance(res, dict):
            all_docs = res.get("docs", []) or []
        elif isinstance(res, list):
            # Backward compatibility if underlying API returns list
            all_docs = res

        paginated_results = all_docs[offset:offset + request.k] if all_docs else []

        # Format items
        items = [_format_article_item(article) for article in paginated_results]

        # Calculate next cursor
        next_cursor = None
        if len(all_docs) > offset + request.k:
            # More results available
            next_cursor = _encode_cursor(offset + request.k)

        # Calculate metrics
        total_available = len(all_docs)
        coverage = min(1.0, len(paginated_results) / request.k) if request.k > 0 else 0.0

        freshness_stats = {
            "median_age_seconds": _calculate_freshness_median(all_docs),
            "window_hours": request.hours
        }

        diagnostics = {
            "total_results": total_available,
            "offset": offset,
            "returned": len(items),
            "has_more": next_cursor is not None,
            "window": window,
            "correlation_id": request.correlation_id
        }

        # Return response
        resp = RetrieveResponse(
            items=items,
            next_cursor=next_cursor,
            total_available=total_available,
            coverage=coverage,
            freshness_stats=freshness_stats,
            diagnostics=diagnostics
        )

        logger.info(
            "[AB]/retrieve done | req_id=%s corr=%s returned=%s total=%s has_more=%s coverage=%.2f window=%s",
            req_id,
            request.correlation_id,
            len(items),
            total_available,
            bool(next_cursor),
            coverage,
            window,
        )
        return resp

    except HTTPException:
        raise
    except Exception as e:
        req_id = locals().get("x_request_id") or locals().get("openai_request_id")
        logger.error(f"[AB]/retrieve fail | req_id={req_id} corr={request.correlation_id} err={e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error_code": ErrorCode.INTERNAL_ERROR, "message": str(e)}
        )


# ============================================================================
# Exception Handlers
# ============================================================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Custom HTTP exception handler"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "timestamp": datetime.utcnow().isoformat()
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """General exception handler"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "error_code": ErrorCode.INTERNAL_ERROR,
                "message": "Internal server error"
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    )


# ============================================================================
# Main Entry Point (for local testing)
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8001"))

    logger.info(f"Starting Search API on port {port}...")

    uvicorn.run(
        "search_api:app",
        host="0.0.0.0",
        port=port,
        reload=True,  # Enable auto-reload for development
        log_level="info"
    )
