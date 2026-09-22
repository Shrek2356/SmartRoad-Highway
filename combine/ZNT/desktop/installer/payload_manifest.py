"""Prepare an immutable, manifest-verified installer payload; never package a live workspace."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
from pathlib import Path, PurePosixPath
from zipfile import ZipFile


def safe_relative(value: str) -> str:
    value = value.replace("\\", "/")
    parts = value.split("/")
    reserved = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
    if any(not part or part in {".", ".."} or part.endswith((".", " "))
           or part.split(".")[0].lower() in reserved
           or any(ord(c) < 32 or c in ':<>"|?*' for c in part) for part in parts):
        raise ValueError(f"Unsafe Windows archive path: {value!r}")
    return "/".join(parts)


def installer_flags(relative: str) -> str:
    """Settings and imported-document seeds belong to users after first installation."""
    normalized = safe_relative(relative).lower()
    # Versioned road workflow templates must update; editable settings remain user-owned.
    config_prefix = "detectmodel/site_safety_openrisk/configs/"
    managed_templates = {config_prefix + name for name in (
        "road_demo.yaml", "road_offline.yaml", "road_standard.yaml", "road_risk_operators.yaml")}
    if normalized in managed_templates:
        return "ignoreversion"
    if normalized == "desktop-settings.json" or normalized.startswith((
        config_prefix,
        "detectmodel/site_safety_openrisk/knowledge_base/",
        "detectmodel/site_safety_openrisk/road_knowledge_base/",
    )):
        return "onlyifdoesntexist uninsneveruninstall"
    return "ignoreversion"


def assert_release_file(relative: str) -> None:
    parts = safe_relative(relative).lower().split("/")
    if any(part in {"app_data", "road_app_data", "road_knowledge_base", "knowledge_base", "outputs", "runtime", "node_modules", ".git", ".venv", "__pycache__", "build"} or part.startswith("build-") for part in parts[:-1]):
        raise ValueError(f"Runtime/developer data must not enter the installer: {relative}")
    if parts[-1] == ".env" or PurePosixPath(parts[-1]).suffix in {".gguf", ".pt", ".pth", ".safetensors", ".log", ".sqlite", ".sqlite3", ".db"}:
        raise ValueError(f"Private state or model weight must not enter the installer: {relative}")


def inno_escape(value: str) -> str:
    return value.replace("{", "{{").replace('"', '""')


def prepare(archive_path: Path, stage: Path) -> dict:
    if stage.exists():
        raise ValueError(f"Staging path already exists: {stage}")
    stage.mkdir(parents=True)
    payload = stage / "payload"
    with ZipFile(archive_path) as archive:
        entries = {}
        root = None
        for info in archive.infolist():
            if info.is_dir():
                continue
            full = safe_relative(info.filename)
            if "/" not in full:
                raise ValueError("Release ZIP must have exactly one top-level directory")
            folder, relative = full.split("/", 1)
            if root is None:
                root = folder
            if folder != root or relative.lower() in entries:
                raise ValueError("Multiple archive roots or case-insensitive duplicate file")
            if stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError("Symbolic links are not allowed in a Windows installer payload")
            entries[relative.lower()] = (relative, info)
        manifest_item = entries.get("release-manifest.json")
        if not manifest_item:
            raise ValueError("Release manifest is missing")
        manifest_bytes = archive.read(manifest_item[1])
        manifest = json.loads(manifest_bytes.decode("utf-8-sig"))
        expected = {}
        for item in manifest:
            relative = safe_relative(item["path"])
            assert_release_file(relative)
            if relative.lower() in expected or relative.lower() == "release-manifest.json":
                raise ValueError("Duplicate/self-referential manifest entry")
            if not re.fullmatch(r"[0-9a-fA-F]{64}", item["sha256"]) or not isinstance(item["bytes"], int) or item["bytes"] < 0:
                raise ValueError("Invalid manifest hash/length")
            expected[relative.lower()] = (relative, item)
        if set(entries) != set(expected) | {"release-manifest.json"}:
            raise ValueError("Archive files do not exactly match the release manifest")
        files = []
        for key, (relative, item) in expected.items():
            contents = archive.read(entries[key][1])
            if len(contents) != item["bytes"] or hashlib.sha256(contents).hexdigest().lower() != item["sha256"].lower():
                raise ValueError(f"Release integrity check failed: {relative}")
            destination = payload.joinpath(*relative.split("/"))
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(contents)
            files.append(relative)
        (payload / "release-manifest.json").write_bytes(manifest_bytes)
        files.append("release-manifest.json")
    lines = []
    for relative in sorted(files, key=str.lower):
        source = payload.joinpath(*relative.split("/"))
        parent = str(PurePosixPath(relative).parent)
        suffix = "" if parent == "." else "\\" + inno_escape(parent.replace("/", "\\"))
        lines.append(f'Source: "{inno_escape(str(source))}"; DestDir: "{{app}}{suffix}"; Flags: {installer_flags(relative)}')
    include = stage / "payload-files.iss"
    include.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    version = json.loads((payload / "pc-admin/package.json").read_text(encoding="utf-8-sig"))["version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Expected a three-component numeric release version")
    metadata = {"version": version, "payload": str(payload), "include": str(include),
                "verified_manifest_files": len(manifest), "unpacked_bytes": sum(item["bytes"] for item in manifest),
                "preserved_seed_files": [p for p in files if "onlyifdoesntexist" in installer_flags(p)]}
    (stage / "payload-info.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("stage", type=Path)
    arguments = parser.parse_args()
    print(json.dumps(prepare(arguments.archive, arguments.stage), ensure_ascii=True))
