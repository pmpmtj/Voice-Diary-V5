#!/usr/bin/env python3
"""
OAuth handler module for Google Drive authentication
Contains server classes and functions for handling OAuth callback
"""
import socket
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Tuple


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """
    HTTP server handler for receiving OAuth callback with authorization code
    """
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        
        query_components = parse_qs(urlparse(self.path).query)
        if 'code' in query_components:
            self.server.auth_code = query_components['code'][0]
            self.wfile.write(b"""
            <html>
            <head><title>Authentication Successful</title></head>
            <body>
            <h1>Authentication Successful!</h1>
            <p>You can now close this window and return to the application.</p>
            </body>
            </html>
            """)
        else:
            self.wfile.write(b"""
            <html>
            <head><title>Authentication Failed</title></head>
            <body>
            <h1>Authentication Failed</h1>
            <p>Please try again or check the application logs for more information.</p>
            </body>
            </html>
            """)
            
    def log_message(self, format, *args):
        # Suppress server logs
        return


def run_local_server(port=0) -> Tuple[HTTPServer, int]:
    """
    Run a local HTTP server for OAuth callback
    
    Args:
        port: Port to run server on (0 for auto-selection)
        
    Returns:
        Tuple of (server, port)
    """
    # Create server with a dynamically allocated port if port=0
    server = HTTPServer(('localhost', port), OAuthCallbackHandler)
    server.auth_code = None
    
    # If port was 0, get the dynamically assigned port
    if port == 0:
        port = server.server_port
        
    return server, port 