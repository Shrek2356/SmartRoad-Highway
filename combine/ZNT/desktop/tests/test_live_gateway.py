"""Real HTTP/WebSocket services behind the exact desktop handler, isolated data."""
import io
import shutil
import socket
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn
from PIL import Image
from websockets.sync.client import connect

APP_ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(APP_ROOT / 'desktop'), str(APP_ROOT / 'detectmodel/Site_Safety_OpenRisk')]
import app_server
import detect_bridge
from site_safety.agents import road_knowledge
from desktop_app import SpaHandler, ReusableThreadingHTTPServer


def serve(app):
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level='error'))
    thread = threading.Thread(target=server.run, kwargs={'sockets':[sock]}, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started: break
        time.sleep(.05)
    assert server.started
    return port, server, thread


def test_real_gateway_login_knowledge_upload_job_media_and_websocket(tmp_path, monkeypatch):
    backend = tmp_path / 'backend'; backend.mkdir()
    original_root = detect_bridge.ROOT
    for name in ['configs','examples','sample_data','submission_artifacts']:
        if (original_root / name).exists(): shutil.copytree(original_root / name, backend / name)
    monkeypatch.setattr(detect_bridge, 'ROOT', backend)
    monkeypatch.setattr(road_knowledge, 'ROOT', backend)
    db = app_server.Database(tmp_path / 'business/test.db'); db.seed_users()
    state = app_server.AppState(db, tmp_path / 'business')
    monkeypatch.setattr(app_server, 'STATE', state)
    business_port, business, bthread = serve(app_server.app)
    bridge = detect_bridge.DetectBridge(default_profile='demo')
    bridge_port, detect, dthread = serve(detect_bridge.create_app(bridge))
    handler = lambda *a, **k: SpaHandler(*a, directory=str(APP_ROOT / 'pc-admin/dist'), proxy_routes={
        '/business-api': business_port, '/detect-api': bridge_port}, **k)
    gateway = ReusableThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=gateway.serve_forever, daemon=True); thread.start()
    root = f'http://127.0.0.1:{gateway.server_port}'
    try:
        with httpx.Client(base_url=root, timeout=15, trust_env=False) as client:
            assert '<html' in client.get('/login').text
            assert client.get('/business-api/api/health').json()['service'] == 'znt-business-api'
            assert client.get('/detect-api/api/detect/health').json()['ok']
            login = client.post('/business-api/api/auth/login', json={'username':'admin','password':'admin123'})
            assert login.status_code == 200
            token = login.json()['token']; headers = {'Authorization': f'Bearer {token}'}
            assert client.get('/business-api/api/whoami', headers=headers).status_code == 200
            assert client.post('/business-api/api/users', headers=headers, json={
                'username':'release_tester','password':'test-pass-only','role':'safety_officer'}).status_code == 200
            assert client.post('/business-api/api/auth/login', json={
                'username':'release_tester','password':'test-pass-only'}).status_code == 200
            text = '道路巡检发现遗撒物后应记录车道位置并提交人工复核。'.encode()
            assert client.post('/detect-api/api/detect/knowledge/upload', files={'file':('test_rule.txt', text)}).status_code == 200
            assert client.post('/detect-api/api/detect/knowledge/upload', files={'file':('test_rule.txt', b' ')}).status_code == 422
            assert (backend/'road_knowledge_base/test_rule.txt').read_bytes() == text
            image = io.BytesIO(); Image.new('RGB',(96,64),'gray').save(image,format='JPEG')
            uploaded = client.post('/detect-api/api/detect/upload', files={'file':('test.jpg',image.getvalue(),'image/jpeg')}, data={'profile':'demo','device_id':'RELEASE-TEST'})
            assert uploaded.status_code == 200, uploaded.text
            job_id = uploaded.json()['job_id']
            for _ in range(120):
                job = client.get(f'/detect-api/api/detect/jobs/{job_id}').json()
                if job['status'] in {'done','error'}: break
                time.sleep(.1)
            assert job['status'] == 'done', job.get('error')
            assert all(s['status'] in {'done','skipped'} for s in job['stages']), job['stages']
            media = client.get(f'/detect-api/api/detect/jobs/{job_id}/media/{job["image_name"]}')
            assert media.status_code == 200 and media.content == image.getvalue()
            assert job['business_sync']['skipped'] is True
            assert db.count('event') == 0, 'Demo must not manufacture database events'
            bridge.jobs.clear()
            assert client.get('/detect-api/api/detect/recent').json()['items'][0]['job_id'] == job_id
            with connect(f'ws://127.0.0.1:{gateway.server_port}/business-api/ws?token={token}', open_timeout=5) as ws:
                assert 'ready' in ws.recv(timeout=5)
                ws.send('ping')
                assert 'pong' in ws.recv(timeout=5)
    finally:
        gateway.stopping = True; gateway.shutdown(); gateway.server_close()
        business.should_exit = True; detect.should_exit = True
        bthread.join(5); dthread.join(5)
        db.conn.close()
