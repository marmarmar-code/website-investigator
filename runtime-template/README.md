# Private runtime template

Copy this directory into a **new private repository**. Never convert that repository to public. Add real targets only in `config/targets.yml` in the private repository.

Before running the public repository workflow:

1. Publish the public engine container.
2. Set the image, version and exact published digest in `engine.lock`.
3. Keep the private runtime repository free of GitHub Actions workflows.
4. Add a write-enabled deploy key for only the private runtime repository as `WI_RUNTIME_DEPLOY_KEY` in the public repository's Actions secrets.
5. Add optional `WI_APPRISE_URLS` to the public repository's Actions secrets.
6. Run the public workflow manually twice and inspect the baseline and unchanged second run.

The example public workflow deliberately has no schedule. Add a cron trigger only after the
manual runs are approved.

The first successful scan creates a baseline and sends no change alert.
