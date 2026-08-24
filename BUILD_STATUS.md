# Build status

Generated: 2026-08-24T10:35:11Z

**Public release status: PUBLISHED**

**Private runtime status: NOT APPROVED FOR REAL TARGETS**

## Local validation

| Check | Result |
|---|---|
| Python compilation | PASS |
| Public/private boundary and secret-pattern scan | PASS |
| Lint | PASS |
| Automated tests | PASS (33 tests) |
| Test coverage measurement | PASS (61% measured; no minimum threshold claimed) |
| GitHub workflow YAML parsing | PASS (3 workflows) |
| Runtime dependency and license review | PASS (55 distributions) |
| Python source and wheel build | PASS |
| Fresh-environment wheel smoke test | PASS |
| CLI help and version smoke test | PASS (0.1.0) |
| Live quick scan against example.com | PASS |
| Live browser-based deep scan against example.com | PASS |
| Local container build and version check | PASS |
| Live browser-based deep scan from container | PASS |
| Private runtime doctor | PASS |
| Private runtime first monitoring pass | PASS |
| Private runtime unchanged second pass | PASS (no new event or file change) |

The live checks used only `example.com`, a reserved documentation domain. They prove that the release could run in the validation environments; they do not prove future availability of other websites or notification services.

## Commands and results

| Command | Result |
|---|---|
| `.venv/bin/python scripts/check_public_boundary.py` | PASS |
| `.venv/bin/python -m compileall -q src tests scripts` | PASS |
| `.venv/bin/python -m ruff check .` | PASS |
| `.venv/bin/python -m pytest --cov=website_investigator --cov-report=term-missing` | PASS: 33 tests, 61% measured coverage |
| `.venv/bin/python scripts/check_workflow_yaml.py ...` | PASS: public, template, and private workflows parsed |
| `.venv/bin/python scripts/check_dependency_licenses.py` | PASS: 55 installed runtime distributions reviewed |
| `.venv/bin/python -m build` | PASS: wheel and source distribution built |
| Fresh Python 3.12 environment: install final wheel with `[all]`; `wi --help`; `wi version` | PASS: version 0.1.0 |
| Fresh environment: quick and deep `wi inspect https://example.com` with JSON and HTML output | PASS: readable schema and report |
| `docker build -t website-investigator:local-validation .` | PASS |
| Local container: `version` and deep inspection of `https://example.com` | PASS |
| Local private runtime: `wi doctor` and two identical monitor runs with `--no-notify` | PASS: second run created no event or file change |
| Anonymous `docker pull` from an empty Docker configuration, pinned by digest | PASS |

Controlled tests also passed for semantic change creation, failed-scan preservation, two-scan removal confirmation, redirect validation, and blocking private, loopback, link-local, reserved, and metadata addresses.

## GitHub publication

| Check | Result |
|---|---|
| Public repository visibility | PASS: public |
| Private runtime repository visibility | PASS: private |
| Public CI | PASS: run `32716520364` |
| Release `v0.1.0` | PASS |
| Container build and provenance attestation | PASS: run `32716595859` |
| Public container digest | `sha256:6c254bc785090647f4bc5b693e779f8e8ae985251da53c659c2ca01d49454a16` |
| Private runtime lock | PASS: exact digest, never `latest` |
| First private manual workflow | BLOCKED: run `32717286535` received no runner because GitHub reported failed account payments or an insufficient spending limit |

The private workflow failure happened before any step ran. It therefore does not prove the visibility gate, digest pull, scan, baseline, report, private commit, redacted logs, or unchanged second run on GitHub.

## Deliberately not activated

- No real monitoring targets are included; the temporary test target was removed.
- No schedule is enabled; workflows are manual-only.
- No Slack or other notification credential is configured.
- Real targets must not be added until the GitHub billing/spending issue is resolved and two manual private runs pass.
