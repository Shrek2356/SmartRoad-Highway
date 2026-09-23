"""Same-origin desktop gateway: fixed local services, HTTP and WebSocket relay."""
from __future__ import annotations

import http.client
import json
import select
import socket
from urllib.parse import urlsplit


class GatewayMixin:
    # Unbuffered reads are important when an HTTP connection upgrades to WebSocket.
    rbufsize = 0
    protocol_version = "HTTP/1.1"
    HOP_HEADERS = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
                   "te", "trailer", "transfer-encoding", "upgrade"}

    def _json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _dispatch(self):
        route = urlsplit(self.path).path
        if route == "/desktop-api/health":
            self._json(200, {"ok": True, "service": "sitesafe-desktop", "version": "1.4.6"})
            return True
        for prefix, port in self.proxy_routes.items():
            if route == prefix or route.startswith(prefix + "/"):
                upstream_path = self.path[len(prefix):] or "/"
                if not upstream_path.startswith("/"):
                    upstream_path = "/" + upstream_path
                if self.headers.get("Upgrade", "").lower() == "websocket":
                    self._websocket(port, upstream_path)
                else:
                    self._proxy(port, upstream_path)
                return True
        if route.startswith(("/api/", "/desktop-api/")):
            self._json(404, {"detail": "接口不存在"})
            return True
        return False

    def _proxy(self, port, path):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=320)
        response_started = False
        try:
            # The UI uploads multipart requests with Content-Length. Reject unsupported
            # chunked bodies explicitly, rather than forwarding a silently empty upload.
            if self.headers.get("Transfer-Encoding"):
                self.close_connection = True
                self._json(411, {"detail": "上传需要 Content-Length"})
                return
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0 or length > 128 * 1024 * 1024:
                self.close_connection = True
                self._json(413, {"detail": "请求体超过128MB"})
                return
            chunks, remaining = [], length
            while remaining:
                chunk = self.rfile.read(min(remaining, 64 * 1024))
                if not chunk:
                    raise OSError("上传连接提前关闭")
                chunks.append(chunk)
                remaining -= len(chunk)
            body = b"".join(chunks) if length else None
            headers = {k: v for k, v in self.headers.items()
                       if k.lower() not in self.HOP_HEADERS | {"host", "content-length"}}
            headers["Host"] = f"127.0.0.1:{port}"
            conn.request(self.command, path, body=body, headers=headers)
            response = conn.getresponse()
            self.send_response(response.status)
            response_started = True
            # Relay binary media without rewriting its MIME type or error status.
            for k, v in response.getheaders():
                if k.lower() not in self.HOP_HEADERS:
                    self.send_header(k, v)
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            if self.command != "HEAD":
                while data := response.read(64 * 1024):
                    self.wfile.write(data)
        except (OSError, ValueError, http.client.HTTPException):
            self.close_connection = True
            if not response_started:
                self._json(502, {"detail": "本地服务未连接，请在运行状态中检查服务"})
        finally:
            conn.close()

    def _websocket(self, port, path):
        self.close_connection = True
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=5) as upstream:
                request = f"{self.command} {path} HTTP/1.1\r\n"
                request += "".join(f"{k}: {v}\r\n" for k, v in self.headers.items() if k.lower() != "host")
                upstream.sendall((request + f"Host: 127.0.0.1:{port}\r\n\r\n").encode("latin-1"))
                upstream.settimeout(None)
                self.connection.settimeout(None)
                # Server shutdown ends idle tunnels too, so closing the app is bounded.
                while not getattr(self.server, "stopping", False):
                    ready, _, _ = select.select([upstream, self.connection], [], [], 0.5)
                    for source in ready:
                        packet = source.recv(64 * 1024)
                        if not packet:
                            return
                        (self.connection if source is upstream else upstream).sendall(packet)
        except OSError:
            return

    def do_GET(self):
        if not self._dispatch():
            super().do_GET()

    def do_HEAD(self):
        if not self._dispatch():
            super().do_HEAD()

    def do_POST(self):
        if not self._dispatch():
            self._json(404, {"detail": "接口不存在"})

    do_PUT = do_POST
    do_PATCH = do_POST
    do_DELETE = do_POST
    do_OPTIONS = do_POST
