from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_PATHS = {
    "config/targets.yml",
    "data/current",
    "data/events",
    "notifications/pending",
    "notifications/delivered",
    ".env",
}
SECRET_PATTERNS = {
    "Slack webhook": re.compile(r"https://hooks\.slack\.com/services/[A-Za-z0-9_/+-]+"),
    "GitHub token": re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    "GitHub fine-grained token": re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    "AWS access key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "Generic private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}
IGNORED_PARTS = {
    ".git",
    ".venv",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "build",
    "dist",
}
PLACEHOLDER_PATTERNS = {
    "GitHub OWNER placeholder": re.compile(r"(?:github\.com|ghcr\.io)/OWNER(?:/|$)"),
}

errors: list[str] = []
for relative in FORBIDDEN_PATHS:
    path = ROOT / relative
    if path.exists():
        errors.append(f"Forbidden public-runtime path exists: {relative}")

for path in ROOT.rglob("*"):
    relative_path = path.relative_to(ROOT)
    if any(part in IGNORED_PARTS for part in relative_path.parts):
        continue
    if path.is_symlink():
        errors.append(f"Symlinks are not allowed in the public repository: {relative_path}")
        continue
    if not path.is_file():
        continue
    raw = path.read_bytes()
    if b"\x00" in raw:
        continue
    text = raw.decode("utf-8", errors="ignore")
    for name, pattern in SECRET_PATTERNS.items():
        if pattern.search(text):
            errors.append(f"Possible {name} in {path.relative_to(ROOT)}")
    for name, pattern in PLACEHOLDER_PATTERNS.items():
        if pattern.search(text):
            errors.append(f"Possible {name} in {path.relative_to(ROOT)}")

if errors:
    print("\n".join(errors), file=sys.stderr)
    raise SystemExit(1)
print("Public/private boundary check passed")
