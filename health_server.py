#!/usr/bin/env python3
"""
Health Check HTTP Server
Runs alongside the Telegram bot to provide health check endpoint for Railway
"""

import os
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
import json
import threading

logger = logging.getLogger(__name__)


class HealthCheckHandler(BaseHTTPRequestHandler):
    """HTTP handler for health checks"""

    def do_GET(self):
        """Handle GET requests"""
        if self.path == '/health':
            self.send_health_response()
        elif self.path == '/':
            self.send_info_response()
        else:
            self.send_404()

    def do_POST(self):
        """Handle POST requests"""
        if self.path == '/retrieve':
            self.handle_retrieve()
        else:
            self.send_404()

    def send_health_response(self):
        """Send health check response"""
        try:
            # Quick database check
            from pg_client_new import PgClient
            db = PgClient()
            with db._cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()

            # Healthy response
            response = {
                "status": "healthy",
                "timestamp": datetime.utcnow().isoformat(),
                "service": "telegram-bot",
                "checks": {
                    "database": "ok"
                }
            }
            self.send_json_response(200, response)

        except Exception as e:
            # Unhealthy response
            response = {
                "status": "unhealthy",
                "timestamp": datetime.utcnow().isoformat(),
                "service": "telegram-bot",
                "error": str(e)
            }
            self.send_json_response(503, response)

    def send_info_response(self):
        """Send service info response"""
        response = {
            "service": "RSS News Telegram Bot + Search API",
            "version": "phase2-3",
            "timestamp": datetime.utcnow().isoformat(),
            "endpoints": {
                "/health": "Health check endpoint (GET)",
                "/retrieve": "Search endpoint for GPT Actions (POST)",
                "/": "Service info (GET)"
            }
        }
        self.send_json_response(200, response)

    def handle_retrieve(self):
        """Handle /retrieve POST requests for search"""
        try:
            # Read request body
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            request_data = json.loads(body.decode())

            # Import RankingAPI
            from ranking_api import RankingAPI
            import asyncio
            import base64

            # Extract parameters
            query = request_data.get('query', '')
            hours = request_data.get('hours', 24)
            k = request_data.get('k', 10)
            filters = request_data.get('filters', {})
            cursor = request_data.get('cursor')
            correlation_id = request_data.get('correlation_id')

            # Decode cursor
            offset = 0
            if cursor:
                try:
                    cursor_json = base64.b64decode(cursor.encode()).decode()
                    cursor_data = json.loads(cursor_json)
                    offset = cursor_data.get('offset', 0)
                except:
                    offset = 0

            # Convert hours to window
            if hours <= 24:
                window = "24h"
            elif hours <= 48:
                window = "48h"
            else:
                window = "72h"

            # Initialize RankingAPI (creates its own DB client)
            ranking_api = RankingAPI()

            # Run async retrieval
            async def do_retrieve():
                k_total = k + offset
                results = await ranking_api.retrieve_for_analysis(
                    query=query,
                    window=window,
                    k_final=k_total,
                    intent="news_current_events",
                    filters=filters
                )
                return results

            # Execute async function
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                results = loop.run_until_complete(do_retrieve())
            finally:
                loop.close()

            # Paginate results
            paginated_results = results[offset:offset + k] if results else []

            # Format items
            items = []
            for article in paginated_results:
                published_at = article.get('published_at', '')
                if hasattr(published_at, 'isoformat'):
                    published_at = published_at.isoformat()

                items.append({
                    'title': article.get('title', 'Untitled'),
                    'url': article.get('url', article.get('link', '')),
                    'source_domain': article.get('source_domain', article.get('domain', article.get('source', 'unknown'))),
                    'published_at': published_at,
                    'snippet': (article.get('snippet') or article.get('summary', ''))[:300] if article.get('snippet') or article.get('summary') else None,
                    'relevance_score': article.get('scores', {}).get('final', article.get('score'))
                })

            # Calculate next cursor
            next_cursor = None
            if len(results) > offset + k:
                cursor_data = {'offset': offset + k}
                cursor_json = json.dumps(cursor_data)
                next_cursor = base64.b64encode(cursor_json.encode()).decode()

            # Calculate metrics
            total_available = len(results)
            coverage = min(1.0, len(results) / k) if k > 0 else 0.0

            # Calculate freshness median
            now = datetime.utcnow()
            freshness_values = []
            for result in results:
                pub_at = result.get('published_at')
                if pub_at:
                    try:
                        if isinstance(pub_at, str):
                            from datetime import datetime as dt
                            pub_time = dt.fromisoformat(pub_at.replace('Z', '+00:00'))
                        else:
                            pub_time = pub_at
                        if pub_time.tzinfo is not None:
                            pub_time = pub_time.replace(tzinfo=None)
                        age_seconds = (now - pub_time).total_seconds()
                        freshness_values.append(age_seconds)
                    except:
                        continue

            median_age = 0.0
            if freshness_values:
                freshness_values.sort()
                mid = len(freshness_values) // 2
                if len(freshness_values) % 2 == 0:
                    median_age = (freshness_values[mid - 1] + freshness_values[mid]) / 2
                else:
                    median_age = freshness_values[mid]

            # Build response
            response = {
                'items': items,
                'next_cursor': next_cursor,
                'total_available': total_available,
                'coverage': round(coverage, 2),
                'freshness_stats': {
                    'median_age_seconds': round(median_age, 2),
                    'window_hours': hours
                },
                'diagnostics': {
                    'total_results': total_available,
                    'offset': offset,
                    'returned': len(items),
                    'has_more': next_cursor is not None,
                    'window': window,
                    'correlation_id': correlation_id
                }
            }

            self.send_json_response(200, response)

        except Exception as e:
            logger.error(f"Retrieve endpoint error: {e}", exc_info=True)
            error_response = {
                'error': {
                    'error_code': 'INTERNAL_ERROR',
                    'message': str(e)
                },
                'timestamp': datetime.utcnow().isoformat()
            }
            self.send_json_response(500, error_response)

    def send_404(self):
        """Send 404 response"""
        self.send_response(404)
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'Not Found')

    def send_json_response(self, status_code, data):
        """Send JSON response"""
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, format, *args):
        """Override to suppress request logging"""
        # Only log errors
        if self.path != '/health':
            logger.info(f"{self.address_string()} - {format % args}")


def start_health_server(port=8080):
    """Start health check server in background thread"""
    try:
        server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
        logger.info(f"✅ Health check server started on port {port}")
        logger.info(f"   GET http://0.0.0.0:{port}/health - Health check")
        logger.info(f"   GET http://0.0.0.0:{port}/ - Service info")

        # Run server in thread
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        return server

    except Exception as e:
        logger.warning(f"⚠️  Failed to start health server: {e}")
        return None


if __name__ == "__main__":
    # Standalone mode for testing
    logging.basicConfig(level=logging.INFO)
    port = int(os.getenv('PORT', '8080'))
    server = start_health_server(port)
    if server:
        print(f"Health server running on port {port}")
        print("Press Ctrl+C to stop")
        try:
            # Keep main thread alive
            import time
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down...")
            server.shutdown()
