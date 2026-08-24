# Website Investigator

Website Investigator is an evidence-first, passive website inspection and monitoring tool for journalists. It turns a URL into a structured dossier and can monitor a **private** target list without exposing that list in the public engine repository.

> Status: functional alpha. The passive scanner, evidence model, detector packs, semantic diff, local reports and public runtime workflow are implemented. Historical Wayback analysis, broad relationship graphs and production-grade distributed scheduling are deliberately deferred.

## Repository boundary

Use two repositories:

1. **Public:** this engine, detector format, tests, documentation and container image.
2. **Private:** targets, observations, events, reports and notification state.

The manual workflow runs in the public repository and checks out the private runtime with a deploy key restricted to that repository. It pulls a version-pinned public container and pushes generated runtime files back only to the private repository. Private runtime data never enters the public Git history or workflow artifacts.

## What it inspects

- redirects, HTTP status and selected headers;
- DNS records and TLS certificate metadata;
- `robots.txt`, including configured crawler policies;
- parsed public security contacts from `security.txt` and advertising declarations from
  `ads.txt` and `app-ads.txt`;
- canonical URLs, feeds, sitemaps, manifests and structured metadata;
- scripts, cookies and third-party domains;
- evidence-backed signals for publishing platforms, paywalls, analytics, consent and advertising technology;
- optional browser rendering and network observation through Playwright.

It does **not** scan ports, brute-force subdomains, test vulnerabilities, bypass access controls or claim ownership from weak technical similarities.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[all]'
playwright install chromium
wi inspect https://example.com --json report.json --html report.html
```

Run an optional browser-assisted scan:

```bash
wi inspect https://example.com --deep --json report.json --html report.html
```

Compare two observations:

```bash
wi compare old.json new.json --output events.json
```

Open a local dossier browser:

```bash
wi serve --runtime ../website-investigator-runtime
```

## Private monitoring

Copy `runtime-template/` into a separate private repository or use the supplied companion template. Add targets only there. Keep the private repository storage-only; run `Private runtime monitor` manually from the public repository.

```bash
wi doctor --runtime ../website-investigator-runtime
wi monitor --runtime ../website-investigator-runtime
```

Notifications are optional. Set one or more [Apprise](https://github.com/caronc/apprise) URLs in the public repository's `WI_APPRISE_URLS` Actions secret, separated by newlines. Unsent notifications remain in the private queue.

## Slack operation

Slack is the user interface; GitHub remains an implementation detail. An approved user runs
`/undersok example.com` and immediately receives a private receipt. A stateless Cloudflare Worker
verifies the Slack signature, encrypts the request and starts the public workflow with ciphertext
only. The pinned public engine reads the encrypted job, writes the target and report only to the
private runtime, and sends the summary plus HTML report to the requester's Slack App Home.

The receiver stores no targets or reports, detailed Worker logging is disabled, and the public
workflow publishes no artifacts. Slack, GitHub and encryption credentials are stored only in their
respective secret stores. See [Slack setup](docs/SLACK_SETUP.md).

The private HTML report is Norwegian and answer-first: it explains the most important findings,
confidence and limitations before placing DNS, TLS, endpoint details and normalized data in a
collapsed technical appendix.

## Privacy and source handling

- No telemetry or automatic crash reporting.
- No central hosted service.
- Raw HTML is hashed, not stored by default.
- Target names are redacted from routine logs when `WI_REDACT_LOGS=1`.
- External requests are limited to the target, DNS resolvers, certificate infrastructure and explicitly enabled data sources.
- Browser subrequests to private, loopback, link-local and metadata-network addresses are blocked on a best-effort basis.

A target website, its DNS provider and the execution platform can still observe requests. This is not an anonymity tool.

## Detector contributions

Detector rules are YAML and require positive and negative fixtures. A rule must state what its evidence proves, likely false positives and confidence thresholds. See `CONTRIBUTING.md`.

## Existing open-source work

This project deliberately composes mature libraries instead of reimplementing HTTP, browser automation, robots parsing, metadata extraction and notifications. `REUSE_REVIEW.md` records the evaluated full applications and the reuse decision.

## License

Apache License 2.0. Dependencies retain their own licenses; see `THIRD_PARTY_NOTICES.md`.
