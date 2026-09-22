"""Thread-serialized updates and atomic replacement for small JSON settings."""
from __future__ import annotations

import copy
import json
import os
import tempfile
import threading
from pathlib import Path

_locks_guard = threading.Lock()
_locks: dict[str, threading.RLock] = {}


def _lock(path: Path):
    key = os.path.normcase(str(path.resolve()))
    with _locks_guard:
        return _locks.setdefault(key, threading.RLock())


def read_json(path: Path, default: dict) -> dict:
    with _lock(path):
        if not path.is_file():
            return copy.deepcopy(default)
        result = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(result, dict):
            raise ValueError("配置必须是 JSON 对象，原文件未修改")
        return result


def update_json(path: Path, update, default: dict) -> dict:
    with _lock(path):
        result = read_json(path, default)
        update(result)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
        temporary = Path(name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
        return result
