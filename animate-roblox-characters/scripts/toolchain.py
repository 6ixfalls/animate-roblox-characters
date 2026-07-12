#!/usr/bin/env python3
"""Offline inventory and safety audit for the Roblox animation toolchain."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import platform
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any


SKILL_DIRECTORY = Path(__file__).resolve().parents[1]
MANIFEST_PATH = SKILL_DIRECTORY / "assets" / "toolchain-manifest.json"
MINIMUM_BLENDER = (4, 5, 0)
MINIMUM_PILLOW = (10, 0, 0)
MAXIMUM_PILLOW = (13, 0, 0)
NETWORK_MODULES = {"http.client", "requests", "socket", "urllib", "urllib.request"}
PROCESS_MODULES = {"subprocess"}


def load_manifest(path: str | Path = MANIFEST_PATH) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    payload = json.loads(source.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or not isinstance(payload.get("components"), list):
        raise ValueError("Unsupported or malformed toolchain manifest")
    return payload


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit_python_source(path: str | Path) -> dict[str, Any]:
    """Report network, process, and dynamic-code capabilities without executing source."""
    source_path = Path(path).expanduser().resolve()
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    imports = set()
    calls = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                parts = []
                current = node.func
                while isinstance(current, ast.Attribute):
                    parts.append(current.attr)
                    current = current.value
                if isinstance(current, ast.Name):
                    parts.append(current.id)
                calls.add(".".join(reversed(parts)))
    network = sorted(
        name for name in imports if name in NETWORK_MODULES or any(name.startswith(item + ".") for item in NETWORK_MODULES)
    )
    processes = sorted(
        name for name in imports if name in PROCESS_MODULES or any(name.startswith(item + ".") for item in PROCESS_MODULES)
    )
    dynamic_calls = sorted(name for name in calls if name in {"eval", "exec", "compile", "os.system"})
    network_calls = sorted(
        name
        for name in calls
        if name.startswith(("requests.", "urllib.", "socket.", "http.client."))
    )
    return {
        "path": str(source_path),
        "sha256": sha256_file(source_path),
        "imports": sorted(imports),
        "network_modules": network,
        "process_modules": processes,
        "dynamic_code_calls": dynamic_calls,
        "network_calls": network_calls,
        "review_required": bool(network or processes or dynamic_calls or network_calls),
    }


def audit_python_archive(path: str | Path) -> dict[str, Any]:
    """Audit every Python file in a zip without importing or executing it."""
    archive_path = Path(path).expanduser().resolve()
    reports = []
    errors = []
    with tempfile.TemporaryDirectory() as directory, zipfile.ZipFile(archive_path) as archive:
        root = Path(directory).resolve()
        for member in archive.infolist():
            target = (root / member.filename).resolve()
            if root not in target.parents and target != root:
                errors.append(f"Unsafe archive member: {member.filename}")
        if errors:
            return {"path": str(archive_path), "sha256": sha256_file(archive_path), "reports": [], "errors": errors}
        archive.extractall(root)
        for source in sorted(root.rglob("*.py")):
            try:
                report = audit_python_source(source)
            except (SyntaxError, UnicodeDecodeError) as exc:
                errors.append(f"Could not audit {source.relative_to(root)}: {exc}")
                continue
            report["path"] = str(source.relative_to(root))
            reports.append(report)
    return {
        "path": str(archive_path),
        "sha256": sha256_file(archive_path),
        "python_files": len(reports),
        "network_files": [item["path"] for item in reports if item["network_modules"] or item["network_calls"]],
        "process_files": [item["path"] for item in reports if item["process_modules"]],
        "dynamic_code_files": [item["path"] for item in reports if item["dynamic_code_calls"]],
        "reports": reports,
        "errors": errors,
    }


def _blender_executable() -> str | None:
    found = shutil.which("blender")
    if found:
        return found
    mac_path = Path("/Applications/Blender.app/Contents/MacOS/Blender")
    return str(mac_path) if mac_path.is_file() else None


def audit_repository(skill_directory: str | Path = SKILL_DIRECTORY) -> dict[str, Any]:
    root = Path(skill_directory).expanduser().resolve()
    manifest = load_manifest(root / "assets" / "toolchain-manifest.json")
    components = []
    errors = []
    warnings = []
    for component in manifest["components"]:
        item = {
            "id": component["id"],
            "bundled": bool(component.get("bundled", False)),
            "license": component.get("license", "unknown"),
            "source": component.get("source"),
            "files": [],
        }
        for relative in component.get("files", []):
            path = root / relative
            exists = path.is_file()
            record = {"path": relative, "exists": exists}
            if exists:
                record["sha256"] = sha256_file(path)
                expected = component.get("sha256") if len(component.get("files", [])) == 1 else None
                if expected:
                    record["expected_sha256"] = expected
                    record["integrity_ok"] = record["sha256"] == expected
                    if not record["integrity_ok"]:
                        errors.append(f"Bundled component failed SHA-256 verification: {relative}")
            else:
                errors.append(f"Missing bundled component file: {relative}")
            item["files"].append(record)
        license_file = component.get("license_file")
        if license_file and not (root / license_file).is_file():
            errors.append(f"Missing third-party license file: {license_file}")
        if component.get("downloads"):
            installed = []
            for download in component["downloads"]:
                path = root / "assets" / "external" / download["destination"]
                record = {"path": str(path.relative_to(root)), "exists": path.is_file()}
                if path.is_file():
                    record["sha256"] = sha256_file(path)
                    record["integrity_ok"] = (
                        record["sha256"] == download["sha256"] and path.stat().st_size == int(download["size"])
                    )
                    if not record["integrity_ok"]:
                        errors.append(f"External asset failed verification: {record['path']}")
                else:
                    warnings.append(
                        f"Pinned external asset is not installed: {record['path']}; run fetch_assets.py for {component['id']}"
                    )
                installed.append(record)
            item["downloads"] = installed
        if component["id"] == "cautioned-blender-addon" and item["files"] and item["files"][0]["exists"]:
            archive_audit = audit_python_archive(root / item["files"][0]["path"])
            item["archive_audit"] = {
                key: archive_audit[key]
                for key in ("python_files", "network_files", "process_files", "dynamic_code_files", "errors")
            }
            errors.extend(archive_audit["errors"])
        components.append(item)
    return {
        "ok": not errors,
        "skill_directory": str(root),
        "components": components,
        "errors": errors,
        "warnings": warnings,
    }


def audit_runtime() -> dict[str, Any]:
    blender = _blender_executable()
    runtime: dict[str, Any] = {
        "blender_executable": blender,
        "uvx_executable": shutil.which("uvx"),
        "inside_blender": False,
        "background": None,
        "session_mode": "not-in-blender",
        "blender_version": None,
        "pillow_version": None,
        "operators": {},
        "agent_checks": {
            "blender_mcp_python_execution": "unverified",
            "roblox_studio_mcp": "optional-unverified",
            "creator_store_animation_plugin": "unverified",
        },
    }
    errors = []
    warnings = []
    try:
        import PIL  # type: ignore
    except ImportError:
        errors.append("Pillow >=10,<13 is required for the final GIF preview")
    else:
        runtime["pillow_version"] = PIL.__version__
        version = tuple(int(part) for part in PIL.__version__.split(".")[:3])
        if version < MINIMUM_PILLOW or version >= MAXIMUM_PILLOW:
            errors.append(f"Unsupported Pillow version: {PIL.__version__}; require >=10,<13")
    try:
        import bpy  # type: ignore
    except ImportError:
        if blender is None:
            errors.append("Blender executable was not found")
        warnings.append("Run inside Blender to verify add-on operators and Blender version")
    else:
        runtime["inside_blender"] = True
        runtime["blender_version"] = list(bpy.app.version)
        runtime["background"] = bool(bpy.app.background)
        runtime["session_mode"] = "background" if bpy.app.background else "persistent-gui"
        if bpy.app.background:
            errors.append(
                "Background Blender sessions are prohibited for animation work; use one persistent "
                "interactive Blender GUI connected through Blender MCP"
            )
        if (
            platform.system().lower() == "darwin"
            and platform.machine().lower() in {"arm64", "aarch64"}
            and tuple(bpy.app.version)[:2] == (5, 1)
        ):
            warnings.append(
                "This Blender/platform combination has produced a native image-thread shutdown crash in "
                "an observed automation session; keep the GUI process open or use Blender 4.5 LTS"
            )
        for name, operator in (
            ("rbxanim_import", bpy.ops.object.rbxanims_importmodel),
            ("rbxanim_rebuild", bpy.ops.object.rbxanims_genrig),
            ("rbxanim_export", bpy.ops.object.rbxanims_bake_file),
        ):
            try:
                operator.get_rna_type()
                available = True
            except (AttributeError, KeyError, RuntimeError):
                available = False
            runtime["operators"][name] = available
        if tuple(bpy.app.version) < MINIMUM_BLENDER:
            errors.append("Blender 4.5 or newer is required")
        if not runtime["operators"].get("rbxanim_export"):
            warnings.append("Motor6D export add-on is not registered in this Blender session")
    return {"ok": not errors, "runtime": runtime, "errors": errors, "warnings": warnings}


def full_audit(skill_directory: str | Path = SKILL_DIRECTORY) -> dict[str, Any]:
    repository = audit_repository(skill_directory)
    runtime = audit_runtime()
    return {
        "ok": repository["ok"] and runtime["ok"],
        "repository": repository,
        "runtime": runtime,
        "errors": repository["errors"] + runtime["errors"],
        "warnings": repository["warnings"] + runtime["warnings"],
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill-directory", default=SKILL_DIRECTORY)
    parser.add_argument("--audit-addon", help="Statically audit a Blender Python add-on without running it")
    parser.add_argument("--audit-archive", help="Statically audit every Python file in an add-on zip")
    parser.add_argument("--repository-only", action="store_true", help="Skip host runtime checks (for CI)")
    return parser.parse_args(argv)


def main() -> int:
    args = _parse_args(sys.argv[1:])
    if args.audit_addon:
        result = audit_python_source(args.audit_addon)
    elif args.audit_archive:
        result = audit_python_archive(args.audit_archive)
        result["ok"] = not result["errors"]
    elif args.repository_only:
        result = audit_repository(args.skill_directory)
    else:
        result = full_audit(args.skill_directory)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok", not result.get("review_required", False)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
