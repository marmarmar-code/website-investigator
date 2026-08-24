# Build status

Generated: 2026-08-24T10:18:33Z

**Release-candidate status: READY FOR GITHUB VALIDATION**

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

The live checks used only `example.com`, a reserved documentation domain. They prove that the release candidate could run in the validation environment; they do not prove future availability of other websites or notification services.

## Publication checks still pending at this commit

- GitHub-hosted CI has not yet run.
- The public GHCR image has not yet been published, so the private `engine.lock` still contains an intentional placeholder digest.
- The private GitHub Actions workflow has not yet pulled the published image by digest.

These checks are performed after this release candidate is pushed. Publication must stop if any required check fails.

## Deliberately not activated

- No real monitoring targets are included.
- No schedule is enabled; workflows are manual-only.
- No Slack or other notification credential is configured.
