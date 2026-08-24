# Third-party notices

Website Investigator is licensed under Apache-2.0. Its installed dependencies remain under their
own licenses. The release checks the complete installed Python runtime dependency graph, including
transitive dependencies, and fails if a package has no reviewed license.

The reviewed runtime packages are grouped below. Exact resolved versions are printed by
`python scripts/check_dependency_licenses.py` during validation and CI.

| License | Runtime packages |
|---|---|
| Apache-2.0 | Playwright, requests, requests-file |
| BSD-2-Clause | Apprise, Pygments |
| BSD-3-Clause or upstream BSD classifier | Click, extruct, HTTP Core, HTTPX, idna, Jinja, lxml, lxml-html-clean, Markdown, MarkupSafe, OAuthLib, Protego, RDFLib, Starlette, tldextract, Uvicorn, w3lib, webencodings |
| ISC | dnspython, requests-oauthlib, Shellingham |
| MIT | annotated-doc, annotated-types, AnyIO, Beautiful Soup, charset-normalizer, FastAPI, filelock, h11, html-text, html5lib, jstyleson, markdown-it-py, mdurl, mf2py, Pydantic, pydantic-core, pyee, pyparsing, PyYAML, Rich, six, Slack Bolt, Slack SDK, Soup Sieve, Typer, typing-inspection, urllib3 |
| MIT and PSF-2.0 | greenlet |
| PSF-2.0 | typing-extensions |
| MPL-2.0 | certifi |
| W3C | pyRdfa3 |

Playwright downloads Chromium for the optional deep scan. Chromium and Debian components in the
container retain their upstream licenses and license files; they are separate executable and system
packages, not copied source in this repository.

No Wappalyzer/WebAppAnalyzer fingerprint database is bundled. Code and signature-data licensing
must be reviewed separately before such data is distributed.
