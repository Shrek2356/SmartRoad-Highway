"""Explicit native save dialog with cancellation and atomic file replacement."""
import base64
import os
import re
import tempfile
from pathlib import Path

MAX_EXPORT_BYTES = 64 * 1024 * 1024
EXTENSIONS = {".pdf", ".csv", ".json", ".md", ".txt", ".png", ".jpg", ".webp"}


def save_export(filename: str, encoded: str, choose_path) -> dict:
    if not isinstance(filename, str) or not isinstance(encoded, str):
        raise ValueError("导出参数无效")
    filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', filename).strip(' .')[:180]
    suffix = Path(filename).suffix.lower()
    if suffix not in EXTENSIONS:
        raise ValueError("不支持的导出格式")
    if len(encoded) > ((MAX_EXPORT_BYTES + 2) // 3) * 4:
        raise ValueError("导出文件超过 64 MB，请缩小导出范围")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("导出内容无效，未写入文件") from exc
    if len(data) > MAX_EXPORT_BYTES:
        raise ValueError("导出文件超过 64 MB")
    selected = choose_path(filename, suffix)
    if not selected:
        return {"status": "cancelled"}
    target = Path(selected)
    if target.suffix.lower() != suffix:
        raise ValueError(f"请使用 {suffix} 扩展名保存，原文件未修改")
    fd, name = tempfile.mkstemp(prefix=".sitesafe-export-", suffix=".tmp", dir=target.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return {"status": "saved", "filename": target.name}
