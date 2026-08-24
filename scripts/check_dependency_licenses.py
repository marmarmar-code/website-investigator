from __future__ import annotations

import importlib.metadata
import sys
from collections import deque

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT_PACKAGE = "website-investigator"
ROOT_EXTRAS = {"all"}
ALLOWED_LICENSES = {
    "Apache 2.0",
    "Apache-2.0",
    "BSD License",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "ISC",
    "ISC License",
    "MIT",
    "MIT AND PSF-2.0",
    "MIT License",
    "MPL-2.0",
    "PSF-2.0",
}
CLASSIFIER_LICENSES = {
    "License :: OSI Approved :: Apache Software License": "Apache-2.0",
    "License :: OSI Approved :: BSD License": "BSD License",
    "License :: OSI Approved :: ISC License (ISCL)": "ISC",
    "License :: OSI Approved :: MIT License": "MIT",
    "License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0",
    "License :: OSI Approved :: W3C License": "W3C",
}


def distribution(name: str) -> importlib.metadata.Distribution:
    try:
        return importlib.metadata.distribution(name)
    except importlib.metadata.PackageNotFoundError as exc:
        raise RuntimeError(f"Required runtime distribution is not installed: {name}") from exc


def dependency_closure() -> list[importlib.metadata.Distribution]:
    selected_extras: dict[str, set[str]] = {
        canonicalize_name(ROOT_PACKAGE): set(ROOT_EXTRAS)
    }
    queue = deque([canonicalize_name(ROOT_PACKAGE)])
    visited_context: dict[str, frozenset[str]] = {}
    distributions: dict[str, importlib.metadata.Distribution] = {}
    environment = default_environment()

    while queue:
        name = queue.popleft()
        extras = selected_extras.get(name, set())
        context = frozenset(extras)
        if visited_context.get(name) == context:
            continue
        visited_context[name] = context
        item = distribution(name)
        distributions[name] = item
        marker_contexts = extras | {""}
        for raw_requirement in item.requires or []:
            requirement = Requirement(raw_requirement)
            if requirement.marker and not any(
                requirement.marker.evaluate({**environment, "extra": extra})
                for extra in marker_contexts
            ):
                continue
            dependency_name = canonicalize_name(requirement.name)
            previous = set(selected_extras.get(dependency_name, set()))
            selected_extras.setdefault(dependency_name, set()).update(requirement.extras)
            if dependency_name not in distributions or previous != selected_extras[dependency_name]:
                queue.append(dependency_name)

    distributions.pop(canonicalize_name(ROOT_PACKAGE), None)
    return sorted(
        distributions.values(),
        key=lambda item: canonicalize_name(item.metadata.get("Name", "")),
    )


def license_name(item: importlib.metadata.Distribution) -> str | None:
    metadata = item.metadata
    value = metadata.get("License-Expression") or metadata.get("License")
    if value and value.strip():
        return value.strip()
    for classifier in metadata.get_all("Classifier", []):
        if classifier in CLASSIFIER_LICENSES:
            return CLASSIFIER_LICENSES[classifier]
    return None


def main() -> int:
    errors: list[str] = []
    inventory: list[tuple[str, str, str]] = []
    try:
        items = dependency_closure()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    for item in items:
        name = item.metadata.get("Name", "<unknown>")
        license_value = license_name(item)
        if license_value not in ALLOWED_LICENSES and license_value != "W3C":
            errors.append(f"{name} {item.version}: unreviewed license {license_value!r}")
        inventory.append((name, item.version, license_value or "UNKNOWN"))
    for name, version, license_value in inventory:
        print(f"{name}\t{version}\t{license_value}")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"Reviewed {len(inventory)} installed runtime distributions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
