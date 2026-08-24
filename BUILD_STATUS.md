# Build status

Generated: 2026-08-24T11:06:16Z

**Public release status: PUBLISHED**

**Private runtime status: MANUAL WORKFLOW VALIDATED; NO REAL TARGETS CONFIGURED**

## Local validation

| Check | Result |
|---|---|
| Python compilation | PASS |
| Public/private boundary and secret-pattern scan | PASS |
| Lint | PASS |
| Automated tests | PASS (34 tests) |
| Test coverage measurement | PASS (64% measured; no minimum threshold claimed) |
| GitHub workflow YAML parsing | PASS (4 public/template workflows; none private) |
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
| `.venv/bin/python -m pytest --cov=website_investigator --cov-report=term-missing` | PASS: 34 tests, 64% measured coverage |
| `.venv/bin/python scripts/check_workflow_yaml.py ...` | PASS: public and template workflows parsed; private runtime contains none |
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
| Public CI for current runtime workflow code | PASS: run `32719889130` |
| Release `v0.1.0` | PASS |
| Container build and provenance attestation | PASS: run `32716595859` |
| Public container digest | `sha256:6c254bc785090647f4bc5b693e779f8e8ae985251da53c659c2ca01d49454a16` |
| Private runtime lock | PASS: exact digest, never `latest` |
| Private repository Actions workflows | PASS: none; the private repository is storage-only |
| Public workflow access to private runtime | PASS: write-enabled deploy key restricted to the private runtime repository and stored only as `WI_RUNTIME_DEPLOY_KEY` |
| First public manual runtime workflow | PASS: run `32719688797`; private visibility boundary, digest pull, baseline, report and private bot commit |
| Second public manual runtime workflow | PASS: run `32719915794`; 1 scanned, 0 failed, 0 events, 0 notifications, no runtime changes and no private commit |
| Public log redaction on final workflow | PASS: no target domain, name or ID in the second public job log |

The earlier private hosted-runner attempt is superseded. Runtime execution now belongs only to the public repository, while targets, observations, reports and notification state remain in the private repository.

## Deliberately not activated

- No real monitoring targets are active; the temporary test target was removed after both manual runs.
- No schedule is enabled; the public runtime workflow is manual-only.
- No Slack or other notification credential is configured.
- The private example baseline and report are retained as audit evidence and never copied into public Git history or artifacts.
