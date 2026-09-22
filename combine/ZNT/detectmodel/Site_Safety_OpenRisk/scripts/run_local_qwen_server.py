"""Launch llama-server from the model paths saved in the platform settings page."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from site_safety.runtime_settings import load_runtime_settings  # noqa: E402


def main() -> int:
    settings = load_runtime_settings()
    server = shutil.which("llama-server") or shutil.which("llama-server.exe")
    if not server:
        print("[错误] 找不到 llama-server.exe，请安装 llama.cpp 或加入 PATH。")
        return 1
    model = Path(settings["qwen_model_path"])
    mmproj = Path(settings["qwen_mmproj_path"])
    parsed = urlparse(settings["qwen_base_url"])
    host = parsed.hostname or "127.0.0.1"
    port = int(parsed.port or 8080)
    if host not in {"127.0.0.1", "localhost", "::1"}:
        print("[错误] 启动脚本只支持本机 Qwen 地址。")
        return 3
    for label, path in (("Qwen 模型", model), ("视觉投影", mmproj)):
        if not path.is_file():
            print(f"[错误] {label}不存在: {path}")
            print("请在 PC 管理端 -> 模型规则配置 -> 模型部件与运行时 中修正路径。")
            return 2
    print(f"llama-server: {server}")
    print(f"model: {model}")
    print(f"endpoint: http://{host}:{port}/v1/chat/completions")
    return subprocess.call(
        [
            server,
            "-m", str(model),
            "--mmproj", str(mmproj),
            "--host", host,
            "--port", str(port),
            "-ngl", "99",
            "-c", "8192",
            "-np", "1",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
