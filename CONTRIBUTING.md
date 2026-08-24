# Contributing

## Principles

1. Passive inspection only by default.
2. Every interpreted finding must preserve concrete evidence.
3. Observation, interpretation and possible relationship are separate concepts.
4. No real newsroom targets, screenshots or private data in tests or issues.
5. New dependencies require a license and maintenance review.

## Detector pull requests

A detector change must include:

- a stable detector ID;
- category and confidence thresholds;
- at least one positive fixture;
- at least one negative fixture;
- a false-positive note;
- evidence that can be shown to a journalist;
- a methodology-version bump when results for existing pages may change.

Run:

```bash
pytest
ruff check .
```
