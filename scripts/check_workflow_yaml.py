from __future__ import annotations

import sys
from pathlib import Path

import yaml


def workflow_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(sorted(path.glob("*.yml")))
            files.extend(sorted(path.glob("*.yaml")))
        else:
            files.append(path)
    return sorted(set(files))


def main(arguments: list[str]) -> int:
    paths = [Path(value) for value in arguments] or [Path(".github/workflows")]
    files = workflow_files(paths)
    if not files:
        print("No workflow YAML files found", file=sys.stderr)
        return 1
    errors: list[str] = []
    for path in files:
        try:
            payload = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
        except yaml.YAMLError as exc:
            errors.append(f"{path}: invalid YAML: {exc}")
            continue
        if not isinstance(payload, dict):
            errors.append(f"{path}: workflow root must be a mapping")
            continue
        for required in ("name", "on", "jobs"):
            if required not in payload:
                errors.append(f"{path}: missing required key {required}")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"Validated {len(files)} workflow YAML file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
