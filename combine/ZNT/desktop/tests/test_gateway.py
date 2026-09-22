import http.client
import json
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from desktop_app import SpaHandler, ReusableThreadingHTTPServer, DesktopRuntime, DEFAULT_CONFIG, http_ready


class EchoHandler(BaseHTTPRequestHandler):
    def handle_request(self):
        if self.headers.get('Upgrade', '').lower() == 'websocket':
            self.send_response(101)
            self.send_header('Upgrade', 'websocket')
            self.send_header('Connection', 'Upgrade')
            self.end_headers()
            data = self.rfile.read(4)
            self.wfile.write(data)
            return
        body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
        self.send_response(422 if self.path == '/bad' else 200)
        self.send_header('Content-Type', self.headers.get('Content-Type', 'application/octet-stream'))
        self.send_header('Content-Length', str(len(body)))
        self.send_header('X-Test-Method', self.command)
        self.send_header('X-Test-Auth', self.headers.get('Authorization', ''))
        self.end_headers()
        self.wfile.write(body)
    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = handle_request
    def log_message(self, *args): pass


@pytest.fixture
def gateway(tmp_path):
    (tmp_path / 'index.html').write_text('<html>app</html>')
    upstream = ThreadingHTTPServer(('127.0.0.1', 0), EchoHandler)
    upthread = threading.Thread(target=upstream.serve_forever, daemon=True); upthread.start()
    handler = lambda *a, **k: SpaHandler(*a, directory=str(tmp_path), proxy_routes={
        '/business-api': upstream.server_port, '/detect-api': upstream.server_port}, **k)
    server = ReusableThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    yield server
    server.stopping = True
    server.shutdown(); server.server_close()
    upstream.shutdown(); upstream.server_close()


@pytest.mark.parametrize('method', ['POST','PUT','PATCH','DELETE','OPTIONS'])
def test_methods_binary_upload_and_auth_are_forwarded(gateway, method):
    client = http.client.HTTPConnection('127.0.0.1', gateway.server_port, timeout=5)
    content = bytes(range(256)) * 1700
    client.request(method, '/detect-api/upload?mode=demo', content,
                   {'Content-Type': 'multipart/form-data; boundary=abc', 'Authorization':'Bearer test-only'})
    result = client.getresponse()
    assert result.status == 200
    assert result.getheader('X-Test-Method') == method
    assert result.getheader('X-Test-Auth') == 'Bearer test-only'
    assert result.read() == content
    client.close()


def test_api_errors_are_not_html(gateway):
    client = http.client.HTTPConnection('127.0.0.1', gateway.server_port)
    client.request('GET','/business-api/bad')
    result = client.getresponse(); result.read()
    assert result.status == 422
    client.request('POST','/unknown')
    result = client.getresponse()
    assert result.status == 404 and 'detail' in json.loads(result.read())
    client.close()


def test_health_rejects_spa_html(gateway):
    root = f'http://127.0.0.1:{gateway.server_port}'
    assert not http_ready(root+'/login', service='znt-business-api')
    assert http_ready(root+'/desktop-api/health', service='sitesafe-desktop')


def test_websocket_upgrade_and_bidirectional_bytes(gateway):
    with socket.create_connection(('127.0.0.1', gateway.server_port), timeout=3) as sock:
        sock.sendall(b'GET /business-api/ws HTTP/1.1\r\nHost: localhost\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n\r\n')
        headers = b''
        while b'\r\n\r\n' not in headers: headers += sock.recv(1)
        assert b'101 Switching Protocols' in headers
        sock.sendall(b'ping')
        assert sock.recv(4) == b'ping'


def test_stopping_shared_services_never_stops_qwen():
    runtime = DesktopRuntime(dict(DEFAULT_CONFIG))
    with patch('desktop_app.urllib.request.urlopen') as call:
        runtime.stop(); runtime.stop()
    call.assert_not_called()


def test_support_folder_is_allowlisted_and_does_not_open_arbitrary_paths(tmp_path):
    runtime = DesktopRuntime(dict(DEFAULT_CONFIG))
    with patch('desktop_app.LOG_DIR', tmp_path / 'logs'), patch('desktop_app.os.startfile', create=True) as opened:
        assert runtime.open_support_folder('logs') == {'opened': True}
        opened.assert_called_once_with(str(tmp_path / 'logs'))
        with pytest.raises(ValueError): runtime.open_support_folder('https://example.com')
        with pytest.raises(ValueError): runtime.open_support_folder('../../private')
        assert opened.call_count == 1


def test_startup_error_is_escaped_and_has_recovery_actions():
    from desktop_app import error_html
    page = error_html('<script>unsafe</script>')
    assert '&lt;script&gt;unsafe&lt;/script&gt;' in page
    assert '<script>unsafe</script>' not in page
    assert '打开运行日志文件夹' in page
    assert '完整解压' in page


def test_spawn_is_rejected_after_stop():
    runtime = DesktopRuntime(dict(DEFAULT_CONFIG))
    runtime.stop()
    with pytest.raises(RuntimeError, match='关闭'):
        runtime._spawn('test', ['never-launch'], Path.cwd())


def test_frontend_cannot_start_after_window_closed():
    runtime = DesktopRuntime(dict(DEFAULT_CONFIG))
    runtime.stop()
    with pytest.raises(RuntimeError, match='取消'):
        runtime.start_frontend()


def test_desktop_settings_persist_without_starting_services(tmp_path, monkeypatch):
    import desktop_app
    target = tmp_path / 'desktop-settings.json'
    monkeypatch.setattr(desktop_app, 'CONFIG_PATH', target)
    monkeypatch.setattr(DesktopRuntime, 'validate', lambda self: None)
    runtime = DesktopRuntime(dict(DEFAULT_CONFIG))
    runtime.save_desktop_settings({'frontend_port': 55173})
    assert runtime.get_desktop_settings()['frontend_port'] == 55173
    assert runtime.frontend_port == 5173
    assert runtime.get_desktop_settings()['restart_required'] is True
    assert runtime.processes == []
