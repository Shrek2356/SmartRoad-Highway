"""Offline workspace snapshots. Call only before business/model services start.

Restores replace only explicit data units, never application code or credentials.
A durable journal recovers interrupted multi-directory swaps on the next launch.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import stat
import tempfile
import uuid
import zipfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

BACKEND = 'detectmodel/Site_Safety_OpenRisk'
UNITS = ('road_app_data', 'road_knowledge_base', 'outputs/road_bridge_jobs',
         'outputs/road_runtime/runtime_settings.json', 'configs/road_runtime_initial_settings.json',
         'configs/road_threshold_overrides.json', 'configs/road_notify_targets.json')
DIRECTORIES = set(UNITS[:3])
MAX_BYTES = 10 * 1024 ** 3
FORMAT = 'sitesafe-workspace-v1'


def _json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('w', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.flush(); os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()


def safe_path(base: Path, relative: str) -> Path:
    parts = PurePosixPath(relative).parts
    if not parts or PurePosixPath(relative).as_posix() != relative or any(part in ('..', '.') or ':' in part or '\\' in part or part.endswith((' ', '.')) for part in parts) or PurePosixPath(relative).is_absolute():
        raise ValueError('备份包含非法路径')
    target = base.joinpath(*parts)
    if not target.resolve().is_relative_to(base.resolve()) or any(p.is_symlink() for p in [target, *target.parents] if p != base.parent):
        raise ValueError('工作空间路径越界或包含链接')
    return target


def allowed(name):
    parts = PurePosixPath(name).parts
    if any(p in {'backups', 'stream_logs', '__pycache__', '.env'} for p in parts): return False
    if Path(name).suffix.lower() in {'.log', '.py', '.exe', '.dll', '.pt', '.pth', '.gguf', '.safetensors', '.tmp'}: return False
    return any((unit not in DIRECTORIES and name == unit) or (unit in DIRECTORIES and name.startswith(unit + '/')) for unit in UNITS)


def export_workspace(root: Path, target: Path) -> dict:
    root, target = root.resolve(), target.resolve()
    backend = root / BACKEND
    # Refuse overwriting an existing archive; no silent destruction by scheduled work.
    if target.exists() or target.suffix.lower() != '.zip': raise ValueError('请选择尚不存在的 .zip 备份文件')
    if target.is_relative_to(backend): raise ValueError('请将备份保存到业务数据目录之外')
    target.parent.mkdir(parents=True, exist_ok=True)
    files = []
    for unit in UNITS:
        path = safe_path(backend, unit)
        candidates = path.rglob('*') if path.is_dir() else [path]
        for item in candidates:
            relative = item.relative_to(backend).as_posix()
            safe_path(backend, relative)
            if item.is_file() and allowed(relative): files.append((relative, item))
    size = sum(p.stat().st_size for _, p in files)
    if size > MAX_BYTES: raise ValueError('工作空间超过 10 GB，请使用独立存储备份方案')
    if shutil.disk_usage(target.parent).free < size + 64 * 1024 ** 2: raise ValueError('备份目标磁盘空间不足')
    fd, temp = tempfile.mkstemp(prefix='.sitesafe-backup-', suffix='.tmp', dir=target.parent)
    os.close(fd)
    temporary = Path(temp)
    try:
        entries = []
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name, path in sorted(files):
                archive.write(path, name)
                entries.append({'path': name, 'bytes': path.stat().st_size, 'sha256': digest(path)})
            archive.writestr('workspace-manifest.json', json.dumps({
                'format': FORMAT, 'created_at': datetime.now(timezone.utc).isoformat(),
                'source_root': str(root), 'units': list(UNITS), 'files': entries,
                'excludes': ['model weights', 'cloud API keys', 'desktop Python/ports', 'logs', 'browser session'],
            }, ensure_ascii=False))
        # Verify the exact bytes written before reporting success.
        inspect_archive(temporary)
        if target.exists(): raise ValueError('目标文件已存在，未覆盖')
        temporary.rename(target)
    finally:
        temporary.unlink(missing_ok=True)
    return {'status': 'saved', 'path': str(target), 'files': len(entries), 'bytes': target.stat().st_size, 'sha256': digest(target)}


def inspect_archive(path: Path, destination: Path | None = None) -> dict:
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        if len(infos) > 100001 or sum(i.file_size for i in infos) > MAX_BYTES:
            raise ValueError('备份超出文件数或大小限制')
        if len({i.filename.casefold() for i in infos}) != len(infos): raise ValueError('备份含重复文件路径')
        info = archive.getinfo('workspace-manifest.json')
        if info.file_size > 20 * 1024 ** 2: raise ValueError('备份清单过大')
        manifest = json.loads(archive.read(info))
        if manifest.get('format') != FORMAT or manifest.get('units') != list(UNITS): raise ValueError('不是兼容的 SmartRoad 工作空间备份')
        if not isinstance(manifest.get('source_root'), str) or not manifest['source_root'].strip(): raise ValueError('备份缺少来源目录信息')
        entries = {e['path']: e for e in manifest['files']}
        if len(entries) != len(manifest['files']) or set(entries) | {'workspace-manifest.json'} != {i.filename for i in infos}:
            raise ValueError('文件清单不完整')
        for name, entry in entries.items():
            safe_path(destination or Path.cwd(), name)
            if not allowed(name): raise ValueError('备份包含非工作空间文件')
            info = archive.getinfo(name)
            if stat.S_ISLNK(info.external_attr >> 16) or info.file_size != entry['bytes']: raise ValueError('文件类型或大小不匹配')
            h = hashlib.sha256()
            output = safe_path(destination, name) if destination else None
            if output: output.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source:
                stream = output.open('wb') if output else None
                try:
                    for block in iter(lambda: source.read(1024 * 1024), b''):
                        h.update(block)
                        if stream: stream.write(block)
                finally:
                    if stream: stream.close()
            if h.hexdigest() != entry['sha256']: raise ValueError('备份文件校验失败，未恢复')
        return manifest


def _rebase(value, old: str, new: str):
    if isinstance(value, dict): return {k: _rebase(v, old, new) for k, v in value.items()}
    if isinstance(value, list): return [_rebase(v, old, new) for v in value]
    if isinstance(value, str):
        normal, prefix = value.replace('\\', '/'), old.replace('\\', '/').rstrip('/')
        if normal.casefold() == prefix.casefold() or normal.casefold().startswith(prefix.casefold() + '/'):
            return new.replace('\\', '/').rstrip('/') + normal[len(prefix):]
    return value


def prepare_data(stage: Path, old_root: str, new_root: str):
    for path in stage.rglob('*'):
        if not path.is_file() or path.suffix not in {'.json', '.jsonl'}: continue
        if path.suffix == '.json':
            _json(path, _rebase(json.loads(path.read_text(encoding='utf-8')), old_root, new_root))
        else:
            rows = [_rebase(json.loads(line), old_root, new_root) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
            path.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows), encoding='utf-8')
    db = stage / 'road_app_data/road_safety.db'
    if db.is_file():
        with closing(sqlite3.connect(db)) as conn:
            if conn.execute('PRAGMA quick_check').fetchone()[0] != 'ok': raise ValueError('业务数据库损坏')
            for identifier, kind, payload in conn.execute('SELECT id,kind,json FROM docs').fetchall():
                data = _rebase(json.loads(payload), old_root, new_root)
                # Restored camera configurations must not immediately start model jobs.
                if kind == 'camera_source': data['desired_running'] = False
                conn.execute('UPDATE docs SET json=? WHERE id=?', (json.dumps(data, ensure_ascii=False), identifier))
            conn.commit()
    for relative in ['outputs/road_runtime/runtime_settings.json', 'configs/road_runtime_initial_settings.json']:
        path = stage / relative
        data = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
        data['qwen_autostart'] = False
        _json(path, data)
    for path in stage.glob('outputs/road_bridge_jobs/JOB-*/bridge_summary.json'):
        data = json.loads(path.read_text(encoding='utf-8'))
        if data.get('status') in {'queued', 'running'}:
            data.update(status='error', error='从备份恢复的未完成任务；请确认模型配置后手动重试')
            _json(path, data)


class WorkspaceMaintenance:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.state = self.root / 'runtime/desktop/workspace'
        self.pending = self.state / 'pending.json'
        self.journal = self.state / 'restore-journal.json'

    def status(self):
        def read(path): return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else None
        return {'pending': read(self.pending), 'last_result': read(self.state / 'last-result.json')}

    def schedule(self, action: str, path: Path):
        if self.pending.exists(): raise ValueError('已有待执行的备份或恢复，请先取消或重启完成')
        path = path.resolve()
        if action == 'restore':
            manifest = inspect_archive(path)
            item = {'action': action, 'path': str(path), 'sha256': digest(path), 'files': len(manifest['files'])}
        elif action == 'backup':
            if path.exists() or path.suffix.lower() != '.zip': raise ValueError('请选择尚不存在的 .zip 文件')
            if path.is_relative_to(self.root / BACKEND): raise ValueError('不能备份到业务数据目录内')
            item = {'action': action, 'path': str(path)}
        else: raise ValueError('不支持的维护操作')
        _json(self.pending, item)
        return self.status()

    def cancel(self):
        self.pending.unlink(missing_ok=True)
        return self.status()

    def rollback(self):
        if not self.journal.is_file(): return
        record = json.loads(self.journal.read_text(encoding='utf-8'))
        if record.get('committed'):
            self.journal.unlink(); return
        recovery = safe_path(self.state, record['recovery'])
        backend = self.root / BACKEND
        for item in reversed(record['units']):
            name = item['path']
            if name not in UNITS: raise ValueError('恢复日志路径无效')
            old, current = safe_path(recovery / 'original', name), safe_path(backend, name)
            if old.exists() or not item['existed']:
                if current.exists():
                    abandoned = safe_path(recovery / 'abandoned', name)
                    abandoned.parent.mkdir(parents=True, exist_ok=True)
                    current.rename(abandoned)
                if old.exists():
                    current.parent.mkdir(parents=True, exist_ok=True); old.rename(current)
        self.journal.unlink()

    def restore(self, path: Path):
        recovery = self.state / ('recovery-' + uuid.uuid4().hex)
        recovery.mkdir(parents=True)
        fresh = recovery / 'incoming'; fresh.mkdir()
        manifest = inspect_archive(path, fresh)
        prepare_data(fresh, manifest['source_root'], str(self.root))
        export_workspace(self.root, recovery / 'before-restore.zip')
        backend = self.root / BACKEND
        record = {'recovery': recovery.name, 'units': [
            {'path': unit, 'existed': safe_path(backend, unit).exists()} for unit in UNITS], 'committed': False}
        _json(self.journal, record)
        try:
            for item in record['units']:
                unit = item['path']; target = safe_path(backend, unit)
                old, incoming = safe_path(recovery / 'original', unit), safe_path(fresh, unit)
                if target.exists():
                    old.parent.mkdir(parents=True, exist_ok=True); target.rename(old)
                if incoming.exists():
                    target.parent.mkdir(parents=True, exist_ok=True); incoming.rename(target)
            record['committed'] = True; _json(self.journal, record)
            self.journal.unlink()
        except Exception:
            self.rollback(); raise
        return {'status': 'restored', 'files': len(manifest['files']), 'recovery_backup': str(recovery / 'before-restore.zip')}

    def run(self, assert_offline):
        if not self.pending.is_file() and not self.journal.is_file(): return None
        try:
            assert_offline()
        except Exception as exc:
            if self.journal.is_file(): raise  # Never start services on a partially restored workspace.
            self.pending.unlink(missing_ok=True)
            result = {'status': 'error', 'message': str(exc), 'completed_at': datetime.now(timezone.utc).isoformat()}
            _json(self.state / 'last-result.json', result)
            return result
        self.rollback()
        if not self.pending.is_file(): return None
        item = json.loads(self.pending.read_text(encoding='utf-8'))
        self.pending.unlink()  # A failed request is not retried automatically on every launch.
        try:
            path = Path(item['path'])
            if item['action'] == 'backup': result = export_workspace(self.root, path)
            else:
                if digest(path) != item['sha256']: raise ValueError('备份在选择后发生变化，请重新选择')
                result = self.restore(path)
        except Exception as exc:
            if self.journal.exists(): raise  # Preserve journal and prevent service startup if rollback failed.
            result = {'status': 'error', 'message': str(exc)}
        result.update(action=item['action'], completed_at=datetime.now(timezone.utc).isoformat())
        _json(self.state / 'last-result.json', result)
        return result
