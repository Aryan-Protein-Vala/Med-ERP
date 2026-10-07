#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pharma Retail - All-in-One Standalone Runnable Server
Serves the High-Speed Counter POS SPA on port 8000 and handles all Frappe
whitelisted API endpoints (/api/method/pharma_retail.api.*) with FEFO allocation,
salt substitutes, Indian GST calculation, and chronic refill reminder generation.
"""

import os
import sys
import json
import mimetypes
import argparse
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime

# Add pharma_retail to python path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.join(BASE_DIR, "apps", "pharma_retail")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

try:
    import frappe
    if hasattr(frappe, "local") and not hasattr(frappe.local, "flags"):
        frappe.local.flags = getattr(frappe, "_dict", dict)(in_test=True, in_request=False)
except Exception:
    pass

from pharma_retail.controllers import gst_taxation
from pharma_retail.tasks import cron_refills
from pharma_retail.api import pos, taxation, refills


class PharmaHTTPRequestHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler supporting both SPA static assets and Frappe API routes."""

    server_version = "PharmaRetail-Server/1.0"

    def _set_cors_headers(self, content_type="application/json; charset=utf-8", status=200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Frappe-CSRF-Token")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()

    def do_OPTIONS(self):
        """Handle CORS pre-flight requests."""
        self._set_cors_headers()

    def _parse_post_data(self):
        """Read and parse incoming POST body (JSON or form-urlencoded)."""
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            return {}
        raw_body = self.rfile.read(content_length).decode("utf-8")
        try:
            return json.loads(raw_body)
        except Exception:
            # Fallback to form data parsing
            parsed = parse_qs(raw_body)
            # Flatten single-item lists
            return {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}

    def _parse_get_params(self, parsed_url):
        """Extract and flatten query string parameters."""
        query_dict = parse_qs(parsed_url.query)
        return {k: v[0] if len(v) == 1 else v for k, v in query_dict.items()}

    def _send_json_response(self, data, status=200):
        """Send JSON response wrapped in Frappe standard structure."""
        self._set_cors_headers("application/json; charset=utf-8", status=status)
        if hasattr(data, "items") and hasattr(data, "success"):
            payload_data = {
                "success": getattr(data, "success", True),
                "count": getattr(data, "count", len(data)),
                "items": list(data),
                "substitutes": list(data),
                **getattr(data, "meta", {})
            }
        else:
            payload_data = data
        # Frappe standard wraps API payloads inside {"message": ...}
        response_payload = {
            "message": payload_data
        }
        self.wfile.write(json.dumps(response_payload, indent=2, default=str).encode("utf-8"))

    def do_HEAD(self):
        """Handle HEAD requests for health checks and uptime monitoring."""
        self._set_cors_headers("text/html; charset=utf-8", status=200)

    def do_GET(self):
        """Handle GET requests for static assets or read-only API endpoints."""
        parsed_url = urlparse(self.path)
        path = parsed_url.path

        # 1. API Route Handling
        if path.startswith("/api/method/"):
            method_name = path[len("/api/method/"):]
            params = self._parse_get_params(parsed_url)
            self._handle_api_call(method_name, params)
            return

        # 2. SPA Static File Serving
        self._serve_static_file(path)

    def do_POST(self):
        """Handle POST requests for transactional and computational API endpoints."""
        parsed_url = urlparse(self.path)
        path = parsed_url.path

        if path.startswith("/api/method/"):
            method_name = path[len("/api/method/"):]
            post_data = self._parse_post_data()
            get_params = self._parse_get_params(parsed_url)
            # Combine params, POST data takes priority
            combined_params = {**get_params, **post_data}
            self._handle_api_call(method_name, combined_params)
            return

        self._send_json_response({"error": "Method Not Allowed"}, status=405)

    def _handle_api_call(self, method_name, params):
        """Route API calls to corresponding Python functions."""
        try:
            try:
                import frappe
                if hasattr(frappe, "local") and not hasattr(frappe.local, "flags"):
                    frappe.local.flags = getattr(frappe, "_dict", dict)(in_test=True, in_request=False)
            except Exception:
                pass

            if method_name in ("pharma_retail.api.pos.search_items", "pos.search_items"):
                query = params.get("query", params.get("q", ""))
                res = pos.search_items(query=query)
                self._send_json_response(res)

            elif method_name in ("pharma_retail.api.pos.get_salt_substitutes", "pos.get_salt_substitutes"):
                salt = params.get("salt_composition", params.get("salt", ""))
                res = pos.get_salt_substitutes(salt_composition=salt)
                self._send_json_response(res)

            elif method_name in ("pharma_retail.api.pos.get_fefo_batches", "pos.get_fefo_batches"):
                item_code = params.get("item_code", "")
                res = pos.get_fefo_batches(item_code=item_code)
                self._send_json_response(res)

            elif method_name in ("pharma_retail.api.pos.create_invoice", "pos.create_invoice"):
                invoice_data = params.get("invoice_data", params)
                res = pos.create_invoice(invoice_data=invoice_data)
                self._send_json_response(res)

            elif method_name in ("pharma_retail.api.taxation.calculate_tax", "taxation.calculate_tax"):
                items = params.get("items", [])
                is_interstate = params.get("is_interstate", False)
                res = taxation.calculate_tax(items=items, is_interstate=is_interstate)
                self._send_json_response(res)

            elif method_name in ("pharma_retail.api.taxation.get_hsn_rate", "taxation.get_hsn_rate"):
                hsn = params.get("hsn_code", "")
                salt = params.get("salt_composition", "")
                name = params.get("item_name", "")
                is_life = params.get("is_lifesaving", False)
                res = taxation.get_hsn_rate(hsn_code=hsn, salt_composition=salt, item_name=name, is_lifesaving=is_life)
                self._send_json_response(res)

            elif method_name in ("pharma_retail.api.refills.get_pending_reminders", "refills.get_pending_reminders"):
                res = refills.get_pending_reminders()
                self._send_json_response(res)

            elif method_name in ("pharma_retail.api.refills.trigger_refill_job", "refills.trigger_refill_job"):
                target_days = params.get("target_days_remaining", params.get("target_days_ahead", 3))
                channel = params.get("channel", "whatsapp")
                res = refills.trigger_refill_job(target_days_ahead=target_days, channel=channel)
                self._send_json_response(res)

            elif method_name in ("ping", "version"):
                self._send_json_response({
                    "status": "online",
                    "app": "pharma_retail",
                    "version": "1.0.0",
                    "site": "pharmacy.local",
                    "timestamp": datetime.now().isoformat()
                })

            else:
                self._send_json_response({
                    "error": f"Unknown method: {method_name}",
                    "supported_methods": [
                        "pharma_retail.api.pos.search_items",
                        "pharma_retail.api.pos.get_salt_substitutes",
                        "pharma_retail.api.pos.get_fefo_batches",
                        "pharma_retail.api.pos.create_invoice",
                        "pharma_retail.api.taxation.calculate_tax",
                        "pharma_retail.api.taxation.get_hsn_rate",
                        "pharma_retail.api.refills.get_pending_reminders",
                        "pharma_retail.api.refills.trigger_refill_job",
                        "ping"
                    ]
                }, status=404)

        except Exception as e:
            self._send_json_response({"error": str(e), "success": False}, status=500)

    def _serve_static_file(self, path):
        """Map URL path to physical static file on disk."""
        pos_dir = os.path.join(APP_DIR, "pharma_retail", "public", "pos")

        # Normalize root and POS URLs to SPA index.html
        if path in ("/", "/pos", "/pos/", "/pharma", "/pharma/"):
            target_file = os.path.join(pos_dir, "index.html")
        elif path in ("/pos.css", "/pos/pos.css"):
            target_file = os.path.join(pos_dir, "pos.css")
        elif path in ("/pos.js", "/pos/pos.js"):
            target_file = os.path.join(pos_dir, "pos.js")
        elif path.startswith("/assets/pharma_retail/"):
            sub_path = path[len("/assets/pharma_retail/"):]
            target_file = os.path.join(APP_DIR, "pharma_retail", "public", sub_path)
        else:
            # Check relative to POS directory
            rel_path = path.lstrip("/")
            target_file = os.path.join(pos_dir, rel_path)

        if os.path.isfile(target_file):
            ctype, _ = mimetypes.guess_type(target_file)
            if not ctype:
                ctype = "application/octet-stream"
            if target_file.endswith(".css"):
                ctype = "text/css"
            elif target_file.endswith(".js"):
                ctype = "application/javascript"

            try:
                with open(target_file, "rb") as f:
                    content = f.read()
                self._set_cors_headers(content_type=ctype, status=200)
                self.wfile.write(content)
            except Exception as e:
                self._send_json_response({"error": f"Error reading file: {e}"}, status=500)
        else:
            # Fallback to SPA index.html for client-side routing
            spa_index = os.path.join(pos_dir, "index.html")
            if os.path.isfile(spa_index):
                with open(spa_index, "rb") as f:
                    content = f.read()
                self._set_cors_headers(content_type="text/html; charset=utf-8", status=200)
                self.wfile.write(content)
            else:
                self._send_json_response({"error": "File not found", "path": path}, status=404)

    def log_message(self, format, *args):
        """Clean terminal logging."""
        sys.stderr.write(f"[{datetime.now().strftime('%H:%M:%S')}] {args[0]} - {args[1]} {args[2]}\n")


def run_server(host="0.0.0.0", port=8000):
    """Start the HTTP server on specified host and port."""
    server_address = (host, port)
    httpd = HTTPServer(server_address, PharmaHTTPRequestHandler)
    print("=" * 70)
    print("  PHARMA RETAIL - ALL-IN-ONE STANDALONE SERVER")
    print("=" * 70)
    print(f"  * Status        : ONLINE")
    print(f"  * Server URL    : http://127.0.0.1:{port}")
    print(f"  * POS SPA       : http://127.0.0.1:{port}/")
    print(f"  * API Endpoint  : http://127.0.0.1:{port}/api/method/...")
    print(f"  * Currency      : INR (₹) | Domain: India")
    print(f"  * Indian GST    : 5%, 12%, 18% Slabs Active (CGST/SGST/IGST)")
    print(f"  * FEFO Picking  : Active (First-Expired First-Out)")
    print(f"  * Refill Cron   : 3-Day SMS/WhatsApp Automation Ready")
    print("=" * 70)
    print("  Press Ctrl+C to stop the server.")
    print("=" * 70)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[!] Shutting down server gracefully...")
        httpd.server_close()
        print("[✓] Server stopped.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pharma Retail Standalone Server")
    parser.add_argument("--host", default="0.0.0.0", help="Binding host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    args = parser.parse_args()

    run_server(host=args.host, port=args.port)
