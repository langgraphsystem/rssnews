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
            "service": "RSS News Telegram Bot",
            "version": "phase2-3",
            "timestamp": datetime.utcnow().isoformat(),
            "endpoints": {
                "/health": "Health check endpoint",
                "/": "Service info"
            }
        }
        self.send_json_response(200, response)

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
