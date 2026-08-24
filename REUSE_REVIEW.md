# Reuse review

Website Investigator composes focused libraries instead of copying an existing scanner or
monitoring application. The choice keeps the public engine passive, inspectable and separate from
private runtime data.

## Reused libraries

- HTTPX for bounded HTTP requests with application-controlled redirects.
- Playwright for the optional browser pass.
- Protego for robots.txt decisions.
- Beautiful Soup and extruct for HTML and structured metadata.
- dnspython and Python's TLS support for public network metadata.
- Pydantic, Typer, Jinja, FastAPI and Uvicorn for models, CLI, reports and the local-only UI.
- Apprise for optional notifications from the private runtime.
- Slack Bolt and the Slack SDK for the optional local Socket Mode command bridge.

## Full applications considered but not embedded

- Wappalyzer-style signature databases were not copied because their code and data licenses need
  separate review and broad fingerprints would weaken the evidence model.
- Vulnerability scanners such as OWASP ZAP are outside scope because this project performs passive
  inspection, not vulnerability testing.
- General change-monitoring and archiving applications couple scheduling, state and presentation
  more tightly than the required public-engine/private-runtime boundary.

No code or detector database from those applications is distributed here. New reuse decisions must
record the source, license, maintenance state, data-handling effect and evidence quality.
