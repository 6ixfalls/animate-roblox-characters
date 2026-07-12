#!/usr/bin/env python3
"""Scan repository files, binary strings, and Git metadata for private data."""

from __future__ import annotations

import argparse
import getpass
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


ALLOWED_GIT_NAMES = {"Roblox Animation Skill Contributors"}
ALLOWED_EMAILS = {"contributors@users.noreply.github.com"}
SKIP_DIRECTORIES = {".git", ".codex", "output", "outputs", "__pycache__", ".pytest_cache", ".mypy_cache"}
SKIP_SUFFIXES = {".pyc", ".pyo", ".blend1", ".blend2"}
MAX_FILE_SIZE = 64 * 1024 * 1024


@dataclass(frozen=True)
class Finding:
    path: str
    rule: str


def _patterns() -> list[tuple[str, re.Pattern[str]]]:
    # Build path tokens in pieces so this scanner does not match its own source.
    mac_home = "/" + "Users" + r"/[^/\s\x00]{1,80}/"
    linux_home = "/" + "home" + r"/[^/\s\x00]{1,80}/"
    windows_home = r"[A-Za-z]:\\" + "Users" + r"\\[^\\\s\x00]{1,80}\\"
    return [
        ("macOS home-directory path", re.compile(mac_home)),
        ("Linux home-directory path", re.compile(linux_home)),
        ("Windows home-directory path", re.compile(windows_home, re.IGNORECASE)),
        ("file URI", re.compile(r"file://(?:/|[A-Za-z]:)")),
        ("email address", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)),
        ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
        ("OpenAI-style secret", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
        ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
        (
            "private key material",
            re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        ),
    ]


def _ascii_strings(data: bytes) -> str:
    return "\n".join(match.decode("ascii", errors="ignore") for match in re.findall(rb"[\x20-\x7e]{6,}", data))


def _iter_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative_parts = path.relative_to(root).parts
        if any(part in SKIP_DIRECTORIES for part in relative_parts):
            continue
        # Source-pinned third-party downloads are intentionally Git-ignored and
        # audited separately before use; they are not publication artifacts.
        if ("assets", "external") in tuple(zip(relative_parts, relative_parts[1:])):
            continue
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        if path.stat().st_size > MAX_FILE_SIZE:
            yield path
            continue
        yield path


def _scan_text(text: str, display_path: str) -> list[Finding]:
    findings = []
    for rule, pattern in _patterns():
        for match in pattern.finditer(text):
            if rule == "email address" and match.group(0).lower() in ALLOWED_EMAILS:
                continue
            findings.append(Finding(display_path, rule))
            break

    local_user = getpass.getuser().strip()
    if local_user and len(local_user) >= 3:
        contextual = re.compile(
            rf"(?:[/\\]|user(?:name)?\s*[:=]\s*){re.escape(local_user)}(?:[/\\\s\"']|$)",
            re.IGNORECASE,
        )
        if contextual.search(text):
            findings.append(Finding(display_path, "current local username"))
    return findings


def scan_file(path: Path, root: Path) -> list[Finding]:
    display_path = path.relative_to(root).as_posix()
    if path.stat().st_size > MAX_FILE_SIZE:
        return [Finding(display_path, "file exceeds privacy scanner size limit")]
    data = path.read_bytes()
    if b"\x00" in data or path.suffix.lower() == ".blend":
        text = _ascii_strings(data)
    else:
        text = data.decode("utf-8", errors="replace")
    return _scan_text(text, display_path)


def _git_output(root: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def scan_git_metadata(root: Path) -> list[Finding]:
    findings = []
    if not (root / ".git").exists():
        return findings

    configured_name = _git_output(root, ["config", "--local", "--get", "user.name"])
    configured_email = _git_output(root, ["config", "--local", "--get", "user.email"])
    if configured_name and configured_name not in ALLOWED_GIT_NAMES:
        findings.append(Finding(".git/config", "non-pseudonymous local Git author name"))
    if configured_email and configured_email.lower() not in ALLOWED_EMAILS:
        findings.append(Finding(".git/config", "non-pseudonymous local Git author email"))

    history = _git_output(root, ["log", "--format=%an%x00%ae%x00%cn%x00%ce"])
    for line in history.splitlines():
        values = line.split("\x00")
        if len(values) != 4:
            continue
        author_name, author_email, committer_name, committer_email = values
        if author_name not in ALLOWED_GIT_NAMES or committer_name not in ALLOWED_GIT_NAMES:
            findings.append(Finding(".git/history", "non-pseudonymous commit author name"))
            break
        if author_email.lower() not in ALLOWED_EMAILS or committer_email.lower() not in ALLOWED_EMAILS:
            findings.append(Finding(".git/history", "non-pseudonymous commit author email"))
            break
    return findings


def scan_repository(root: str | Path) -> list[Finding]:
    root_path = Path(root).expanduser().resolve()
    if not root_path.is_dir():
        raise ValueError("Repository root must be an existing directory")
    findings = []
    for path in _iter_files(root_path):
        findings.extend(scan_file(path, root_path))
    findings.extend(scan_git_metadata(root_path))
    return sorted(set(findings), key=lambda finding: (finding.path, finding.rule))


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=Path(__file__).resolve().parents[2])
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main() -> int:
    args = _parse_args(sys.argv[1:])
    try:
        findings = scan_repository(args.root)
    except (OSError, ValueError) as exc:
        print(f"Privacy check could not run: {exc}", file=sys.stderr)
        return 2
    if args.json_output:
        print(json.dumps({"ok": not findings, "findings": [asdict(item) for item in findings]}, indent=2))
    elif findings:
        print("Privacy check failed:")
        for finding in findings:
            print(f"- {finding.path}: {finding.rule}")
    else:
        print("Privacy check passed: no private paths, personal emails, local identity, or common secrets detected.")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
