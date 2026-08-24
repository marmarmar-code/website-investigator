# Security policy

## Scope

Website Investigator accepts untrusted URLs and HTML. Treat scans as network-facing operations.

## Safe-use rules

- Run the public engine in a disposable container for untrusted targets.
- Do not grant the container access to host secrets, Docker sockets or internal networks.
- Keep the runtime repository private.
- Pin the public container by digest before production use.
- Never run pull-request code with private runtime secrets.
- Keep Slack app and bot tokens in macOS Keychain; never put them in repository files, logs or
  command-line arguments.
- Slack-requested targets and reports are sent to Slack and the private runtime only. The bridge
  uses Socket Mode and opens no inbound public server.
- By default, any member of the installed workspace can request a scan, but the result is delivered
  only to that member's private App Home. Use the private user/channel allowlists when tighter
  access is required.

## Known alpha limitations

The scanner rejects obvious private, loopback, link-local, reserved and cloud metadata destinations before each top-level request. Browser subrequests are filtered as well. DNS rebinding protection is best-effort, not a formal network sandbox. Production deployment should add network-level egress rules that deny private address ranges.

Report vulnerabilities privately through the future repository security-advisory channel. Do not include real newsroom targets in public issues.
