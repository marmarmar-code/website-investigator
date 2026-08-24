# Build status

Generated: 2026-08-24T12:05:46Z

**Public release status: v0.2.0 PUBLISHED AND ANONYMOUSLY RETRIEVABLE**

**Private runtime status: PINNED TO v0.2.0; SLACK CONFIG PRESENT BUT NOT ACTIVATED**

## Local validation

| Check | Result |
|---|---|
| Python compilation | PASS |
| Public/private boundary and secret-pattern scan | PASS |
| Lint | PASS |
| Automated tests | PASS (52 tests) |
| Test coverage measurement | PASS (61% measured; no minimum threshold claimed) |
| GitHub workflow YAML parsing | PASS (4 public/template workflows; none private) |
| Runtime dependency and license review | PASS (57 distributions) |
| Python source and wheel build | PASS |
| Fresh-environment wheel smoke test | PASS |
| CLI help and version smoke test | PASS (0.2.0) |
| Live quick scan against example.com | PASS |
| Live browser-based deep scan against example.com | PASS |
| Local container build and version check | PASS (0.2.0; Slack CLI present) |
| Live browser-based deep scan from container | PASS |
| Private runtime doctor | PASS |
| Private runtime first monitoring pass | PASS |
| Private runtime unchanged second pass | PASS (no new event or file change) |
| Slack command parsing, workspace binding, private-DM routing and Keychain handling | PASS |
| Slack app manifest and least-privilege scopes | PASS (`commands`, `chat:write`, `files:write`) |
| Fresh wheel with Slack extra | PASS (Slack Bolt 1.30.0; Slack SDK 3.43.0) |
| Live deep scan through Slack job pipeline with a capture adapter | PASS (example.com; private summary and report prepared; no invoking-channel output) |
| Live Slack workspace receipt | NOT RUN (app and credentials not configured) |

The live checks used only `example.com`, a reserved documentation domain. They prove that the release could run in the validation environments; they do not prove future availability of other websites or notification services.

## Commands and results

| Command | Result |
|---|---|
| `.venv/bin/python scripts/check_public_boundary.py` | PASS |
| `.venv/bin/python -m compileall -q src tests scripts` | PASS |
| `.venv/bin/python -m ruff check .` | PASS |
| `.venv/bin/python -m pytest --cov=website_investigator --cov-report=term-missing` | PASS: 52 tests, 61% measured coverage |
| `.venv/bin/python scripts/check_workflow_yaml.py ...` | PASS: public and template workflows parsed; private runtime contains none |
| `.venv/bin/python scripts/check_dependency_licenses.py` | PASS: 57 installed runtime distributions reviewed |
| `.venv/bin/python -m build` | PASS: 0.2.0 wheel and source distribution |
| Fresh Python 3.12 environment: install the 0.2.0 wheel with `[slack,deep]`; run Slack CLI/import smoke | PASS: version 0.2.0 |
| Fresh environment: quick and deep `wi inspect https://example.com` with JSON and HTML output | PASS: readable schema and report |
| `docker build -t website-investigator:local-validation .` | PASS |
| Local container: `version` and deep inspection of `https://example.com` | PASS |
| Local private runtime: `wi doctor` and two identical monitor runs with `--no-notify` | PASS: second run created no event or file change |
| Anonymous `docker pull` from an empty Docker configuration, pinned by digest | PASS |
| Live example.com deep scan through `process_slack_job` with a non-networking Slack capture adapter | PASS: success, zero scan errors, two private messages, one private report file, no output to the invoking channel |

Controlled tests also passed for semantic change creation, failed-scan preservation, two-scan removal confirmation, redirect validation, and blocking private, loopback, link-local, reserved, and metadata addresses.

## GitHub publication

| Check | Result |
|---|---|
| Public repository visibility | PASS: public |
| Private runtime repository visibility | PASS: private |
| Public CI for the v0.2.0 runtime code | PASS: run `32724524215` |
| Tag CI for `v0.2.0` | PASS: run `32724602286` |
| Release `v0.2.0` | PASS |
| Container build and provenance attestation | PASS: run `32724602396` |
| Public container digest | `sha256:617d6c1199517cb1c06bf28c367ad06c40065a017a56022f1030743a67379a9b` |
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
- No Slack credential is configured yet.
- The Slack bridge is implemented but disabled. No Slack app is installed, no background service is
  active, and no real Slack message or file receipt has been verified yet.
- The private example baseline and report are retained as audit evidence and never copied into public Git history or artifacts.
