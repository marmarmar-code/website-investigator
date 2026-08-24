# Working rules

- Keep this repository public-safe: no real monitoring targets, secrets, runtime state, raw captures, or private editorial notes.
- Preserve the boundary to the separate private runtime repository.
- Keep inspection passive. Do not add port scanning, vulnerability scanning, access-control bypasses, telemetry, or a central service.
- Validate every redirect and browser request against the SSRF rules.
- Do not weaken tests to hide failures. Record only commands and results that were actually run.
- Use synthetic fixtures only for automated tests, never as evidence that a real user workflow works.
- Keep release and dependency changes small, reviewable, and compatible with Python 3.12.
