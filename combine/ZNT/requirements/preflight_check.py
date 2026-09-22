"""ZNT deployment preflight and guided environment checker (stdlib only)."""
from __future__ import annotations

import argparse
import contextlib
import importlib
import importlib.util
import io
import json
import os
import platform
import shutil
import subprocess
import sys
import struct
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DETECT_ROOT = ROOT / "detectmodel" / "Site_Safety_OpenRisk"
SETTINGS_PATH = DETECT_ROOT / "configs" / "road_runtime_initial_settings.json"
MANIFEST_PATH = Path(__file__).with_name("deployment-manifest.json")
REPORT_PATH = ROOT / "runtime" / "deployment_preflight.json"

BASE_DEPENDENCIES = {
    "fastapi": "FastAPI",
    "uvicorn": "Uvicorn",
    "multipart": "python-multipart",
    "dotenv": "python-dotenv",
    "httpx": "HTTPX",
    "psutil": "psutil",
    "yaml": "PyYAML",
    "pydantic": "Pydantic",
    "PIL": "Pillow",
    "numpy": "NumPy",
    "sklearn": "scikit-learn (RAG index)",
    "pypdf": "pypdf (PDF standards)",
    "docx": "python-docx (DOCX standards)",
}
FULL_DEPENDENCIES = {
    "cv2": "OpenCV",
    "torchvision": "torchvision (must match PyTorch)",
    "sam3.model_builder": "SAM3 model builder",
}


def command_output(command: list[str]) -> str:
    executable = shutil.which(command[0])
    if executable:
        command = [executable, *command[1:]]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=8, check=False,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return (result.stdout or result.stderr or "").strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def version_tuple(text: str) -> tuple[int, ...]:
    values: list[int] = []
    for part in text.lstrip("v").split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        if not digits:
            break
        values.append(int(digits))
    return tuple(values)


def dependency_info(mode: str) -> dict[str, Any]:
    expected = dict(BASE_DEPENDENCIES)
    if mode in {"offline", "cloud"}:
        expected.update(FULL_DEPENDENCIES)
    missing, failures = [], {}
    for module, label in expected.items():
        try:
            importlib.import_module(module)
        except Exception as exc:
            missing.append(label)
            failures[label] = f"{type(exc).__name__}: {exc}"
    return {"ready": not missing, "missing": missing, "failures": failures, "checked": list(expected.values())}


def gpu_info() -> dict[str, Any]:
    query = command_output(
        ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"]
    )
    if not query:
        return {"available": False, "devices": []}
    devices = []
    for line in query.splitlines():
        parts = [item.strip() for item in line.split(",")]
        if len(parts) >= 3:
            try:
                devices.append({"name": parts[0], "vram_mb": int(float(parts[1])), "driver": parts[2]})
            except ValueError:
                continue
    return {"available": bool(devices), "devices": devices}


def torch_info() -> dict[str, Any]:
    try:
        import torch

        return {
            "installed": True,
            "version": str(torch.__version__),
            "cuda_build": str(torch.version.cuda),
            "cuda_available": bool(torch.cuda.is_available()),
        }
    except Exception as exc:  # the checker must survive a broken torch install
        return {"installed": False, "error": f"{type(exc).__name__}: {exc}"}


def load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        return value if isinstance(value, dict) else default
    except (OSError, ValueError, json.JSONDecodeError):
        return default


def resolve_model_path(value: str) -> Path:
    path = Path(os.path.expandvars(os.path.expanduser(value)))
    return (path if path.is_absolute() else DETECT_ROOT / path).resolve()


def desktop_python(root: Path = ROOT) -> Path:
    """A configured desktop interpreter is authoritative, even when it is broken."""
    config_path = root / "desktop-settings.json"
    if config_path.is_file():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8-sig"))
            value = str(config.get("backend_python") or "python-runtime/python.exe")
        except (OSError, ValueError, AttributeError) as exc:
            raise RuntimeError("desktop-settings.json 无法读取，请修复桌面 Python 配置。") from exc
        path = Path(os.path.expandvars(value)).expanduser()
        return (path if path.is_absolute() else root / path).resolve()
    for relative in ("env/Scripts/python.exe", "env/python.exe", "python-runtime/python.exe"):
        path = root / relative
        if path.is_file():
            return path.resolve()
    return Path(sys.executable).resolve()


def run_probe(python: Path, mode: str, *, runner=None) -> dict[str, Any]:
    """Bounded child check; never accepts shell commands, installs packages or starts models."""
    if mode not in {"demo", "offline", "cloud"}:
        raise ValueError("未知检测模式")
    if not python.is_file():
        raise RuntimeError(f"所选 Python 不存在：{python}。请在系统设置 → 桌面与连接重新选择。")
    clean_env = {k: v for k, v in os.environ.items() if k.upper() not in {"PYTHONPATH", "PYTHONHOME"}}
    try:
        result = (runner or subprocess.run)(
            [str(python), "-I", "-X", "utf8", str(Path(__file__).resolve()), "--mode", mode, "--json"],
            cwd=str(ROOT), env=clean_env, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=90, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("环境检查超过 90 秒，已停止本次检查；请查看环境是否存在损坏的依赖。模型未启动。") from exc
    except OSError as exc:
        raise RuntimeError(f"无法执行所选 Python：{python}") from exc
    try:
        report = json.loads(result.stdout)
        if not isinstance(report, dict) or not isinstance(report.get("ready"), bool) or report.get("mode") != mode or result.returncode not in {0, 2}:
            raise ValueError("unexpected report")
        if report.get("error"):
            raise RuntimeError(f"环境检查未完成：{report['error']}")
        if not isinstance(report.get("system"), dict):
            raise ValueError("missing system information")
    except (ValueError, TypeError) as exc:
        raise RuntimeError("所选 Python 未返回有效诊断报告；请检查 Python 安装和 requirements 目录是否完整。") from exc
    return report


def collect(mode: str) -> dict[str, Any]:
    manifest = load_json(MANIFEST_PATH, {})
    settings = load_json(SETTINGS_PATH, {})
    settings.update(load_json(DETECT_ROOT / "outputs" / "runtime" / "runtime_settings.json", {}))
    gpu = gpu_info()
    torch = torch_info() if mode in {"offline", "cloud"} else {
        "installed": importlib.util.find_spec("torch") is not None,
        "cuda_available": False,
        "skipped": True,
        "note": "Demo mode does not require or initialize PyTorch/CUDA.",
    }
    dependencies = dependency_info(mode)
    node_text = command_output(["node", "--version"])
    npm_text = command_output(["npm", "--version"])
    disk = shutil.disk_usage(ROOT)
    physical_ram_gb = None
    try:
        import psutil

        physical_ram_gb = round(psutil.virtual_memory().total / 1024**3, 1)
    except Exception:
        pass

    model_checks: dict[str, Any] = {}
    for key, spec in manifest.get("models", {}).items():
        configured = str(settings.get(key) or "")
        path = resolve_model_path(configured) if configured else None
        exists = bool(path and (path.is_file() or (key == "sam3_repo_path" and path.is_dir())))
        required = mode in spec.get("required_for", [])
        model_checks[key] = {
            "label": spec.get("label", key),
            "configured": configured,
            "resolved": str(path) if path else "",
            "exists": exists,
            "required": required,
            "source": spec.get("source", ""),
        }

    sam_repo_value = str(settings.get("sam3_repo_path") or "")
    sam_repo = resolve_model_path(sam_repo_value) if sam_repo_value else None
    model_checks["sam3_repo_path"] = {
        "label": "SAM3 source repository",
        "configured": sam_repo_value,
        "resolved": str(sam_repo) if sam_repo else "",
        "exists": bool(sam_repo and sam_repo.is_dir()),
        "required": mode in {"offline", "cloud"},
        "source": "https://github.com/facebookresearch/sam3",
    }

    max_vram_gb = max((d["vram_mb"] for d in gpu["devices"]), default=0) / 1024
    # Demo 交付包固定使用已验证的 Python 3.12 便携运行时；完整 GPU 环境仍推荐 3.10。
    python_ok = sys.version_info[:2] in {(3, 10), (3, 12)}
    node_ok = bool(node_text) and version_tuple(node_text)[:1] in {(20,), (22,), (24,)}
    configured_llama = str(settings.get("llama_server_path") or "").strip()
    llama_path = resolve_model_path(configured_llama) if configured_llama else None
    llama_server = (str(llama_path) if llama_path.is_file() else None) if llama_path else (shutil.which("llama-server") or shutil.which("llama-server.exe"))
    model_checks["llama_server_path"] = {
        "label": "llama.cpp 推理引擎", "configured": configured_llama,
        "resolved": llama_server or (str(llama_path) if llama_path else ""),
        "exists": bool(llama_server), "required": mode == "offline",
        "source": "https://github.com/ggml-org/llama.cpp/releases",
    }
    if mode != "demo" and settings.get("clip_enabled"):
        model_checks["clip_checkpoint_path"]["required"] = True
        try:
            importlib.import_module("open_clip")
        except Exception as exc:
            dependencies["missing"].append("OpenCLIP（当前已启用）")
            dependencies["failures"]["OpenCLIP"] = f"{type(exc).__name__}: {exc}"
            dependencies["ready"] = False
    static_desktop = (ROOT / "pc-admin" / "dist" / "index.html").is_file()
    issues: list[dict[str, str]] = []

    if struct.calcsize("P") != 8:
        issues.append({"level": "error", "message": "需要 64 位 Python；请重新选择 x64 环境。"})

    if dependencies["missing"]:
        issues.append({
            "level": "error",
            "message": "当前 Python 缺少依赖：" + ", ".join(dependencies["missing"])
            + "。请对下方显示的【当前检测 Python】安装 requirements/detect-full.txt（Demo 使用 detect-bridge.txt）；SAM3 另行安装。不要对另一个 Python 安装。",
        })

    if not python_ok or (mode != "demo" and sys.version_info < (3, 12)):
        issues.append({"level": "warning", "message": "新建官方 SAM3 环境使用 Python 3.12（当前上游要求 3.12+）。3.10 仅对应历史适配环境，不要直接混装最新 SAM3。"})
    if not node_ok and not static_desktop:
        issues.append({"level": "error", "message": "未找到可用 Node.js；推荐安装 Node.js 20/22 LTS。"})
    elif node_ok and not npm_text and not static_desktop:
        issues.append({"level": "error", "message": "Node.js 可用但 npm 不可用；请修复 Node.js 安装或 PATH。"})
    if mode in {"offline", "cloud"} and not torch.get("cuda_available"):
        issues.append({"level": "error", "message": "完整检测需要 CUDA 版 PyTorch，当前 Python 未检测到可用 CUDA。"})
    if mode == "offline" and max_vram_gb < 12:
        issues.append({"level": "error", "message": "本地离线模式建议至少 12 GB 显存，推荐 16 GB 以上。"})
    if mode == "cloud" and max_vram_gb < 8:
        issues.append({"level": "warning", "message": "云端视觉模式仍需本地运行 SAM3，建议至少 8 GB 显存。"})
    if mode == "offline" and not llama_server:
        issues.append({"level": "error", "message": "未找到 llama-server.exe；本地 Qwen 无法由平台自动启动。"})
    for flag, label in (("qwen_enabled", "Qwen"), ("sam3_enabled", "SAM3")):
        required = mode != "demo" and (flag != "qwen_enabled" or mode == "offline")
        if required and settings.get(flag) is False:
            issues.append({"level": "error", "message": f"{label} 组件尚未激活，请在模型部件与运行时开启。"})
    try:
        selected_python = desktop_python()
        if selected_python != Path(sys.executable).resolve():
            issues.append({"level": "error", "message": "当前检测桥仍在旧 Python 运行，与桌面保存的环境不同；请关闭并重新打开软件，再检查。"})
    except RuntimeError as exc:
        selected_python = None
        issues.append({"level": "error", "message": str(exc)})
    if disk.free / 1024**3 < 20:
        issues.append({"level": "warning", "message": "剩余磁盘不足 20 GB；模型、环境和结果文件可能无法完整落盘。"})
    for check in model_checks.values():
        if check["required"] and not check["exists"]:
            issues.append({"level": "error", "message": f"缺少 {check['label']}：{check['resolved'] or '尚未配置'}"})

    if mode == "demo":
        recommendation = "演示模式可运行：无需模型权重和 NVIDIA GPU，只验证前端、业务后端与 Mock 链路。"
    elif mode == "cloud":
        recommendation = "云端视觉模式：配置兼容的多模态 API，同时在本地保留 SAM3 和 CUDA PyTorch。"
    else:
        recommendation = "本地离线模式：Qwen GGUF + 匹配 mmproj + llama.cpp + SAM3 全部在本机运行。"

    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "mode": mode,
        "scope": "仅环境、组件导入和文件存在性检查；不下载权重、不启动模型、不发送云端请求，不代表真实推理验收。",
        "next_step": "保存模型路径并启动对应服务，再到实时检测提交一张新图片；成功后完成八图回归。",
        "recommendation": recommendation,
        "system": {
            "os": platform.platform(),
            "python": sys.version.split()[0],
            "python_executable": sys.executable,
            "desktop_python": str(selected_python) if selected_python else None,
            "node": node_text or None,
            "prebuilt_frontend": static_desktop,
            "npm": npm_text or None,
            "ram_gb": physical_ram_gb,
            "disk_free_gb": round(disk.free / 1024**3, 1),
            "gpu": gpu,
            "torch": torch,
            "dependencies": dependencies,
            "llama_server": llama_server,
        },
        "models": model_checks,
        "issues": issues,
        "ready": not any(item["level"] == "error" for item in issues),
    }


def print_report(report: dict[str, Any]) -> None:
    system = report["system"]
    print("\n=== ZNT 新部署智能引导 ===")
    print(f"模式: {report['mode']}  |  {'可继续部署' if report['ready'] else '存在阻断项'}")
    print(report["recommendation"])
    print(f"当前检测 Python: {system['python']}  ({system['python_executable']})")
    print(f"Node/npm: {system['node'] or '未安装'} / {system['npm'] or '未安装'}")
    print(f"内存/磁盘: {system['ram_gb'] or '未知'} GB / 剩余 {system['disk_free_gb']} GB")
    devices = system["gpu"]["devices"]
    print("GPU: " + ("; ".join(f"{d['name']} ({d['vram_mb']/1024:.1f} GB)" for d in devices) or "未检测到 NVIDIA GPU"))
    torch = system["torch"]
    if torch.get("skipped"):
        print("PyTorch: Demo 模式无需检查")
    else:
        print(f"PyTorch: {torch.get('version', '未安装')} | CUDA可用: {torch.get('cuda_available', False)}")
    dependencies = system["dependencies"]
    print("Python依赖: " + ("已就绪" if dependencies["ready"] else "缺少 " + ", ".join(dependencies["missing"])))
    print(f"llama-server: {system['llama_server'] or '未找到'}")
    print("\n模型与组件:")
    for check in report["models"].values():
        tag = "OK" if check["exists"] else ("缺失" if check["required"] else "可选未配")
        required = "必需" if check["required"] else "可选"
        print(f"  [{tag}] {check['label']} ({required})")
        if check["resolved"]:
            print(f"       {check['resolved']}")
        if not check["exists"] and check["source"]:
            print(f"       来源/说明: {check['source']}")
    print("\n诊断:")
    if report["issues"]:
        for item in report["issues"]:
            print(f"  [{item['level'].upper()}] {item['message']}")
    else:
        print("  未发现问题。可运行 start-platform.bat。")
    print("\n详细步骤: requirements\\DEPLOYMENT_GUIDE.md")
    print(report.get("scope", ""))
    print("云端模式还须在前端填写并测试 API；本检查不验证密钥、访问权限、模型配对或实际推理结果。")


def main() -> int:
    parser = argparse.ArgumentParser(description="ZNT deployment preflight")
    parser.add_argument("--mode", choices=["demo", "offline", "cloud"], default="offline")
    parser.add_argument("--save", action="store_true", help="save machine-readable report")
    parser.add_argument("--json", action="store_true", help="output JSON only")
    parser.add_argument("--use-desktop-python", action="store_true", help="check the desktop-selected interpreter")
    args = parser.parse_args()
    try:
        if args.use_desktop_python:
            report = run_probe(desktop_python(), args.mode)
        else:
            # Third-party import banners must not corrupt the machine-readable response.
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                report = collect(args.mode)
    except Exception as exc:
        if args.json:
            print(json.dumps({"ready": False, "mode": args.mode, "error": str(exc)}, ensure_ascii=False))
        else:
            print(f"[错误] {exc}")
        return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        print_report(report)
    if args.save:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        if not args.json:
            print(f"\n报告已保存: {REPORT_PATH}")
    return 0 if report["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
