# Private runtime template

Copy this directory into a **new private repository**. Never convert that repository to public. Add real targets only in `config/targets.yml` in the private repository.

Before enabling the workflow:

1. Publish the public engine container.
2. Set the image, version and exact published digest in `engine.lock`.
3. Add optional `WI_APPRISE_URLS` as a repository secret.
4. Keep Actions permissions restricted to repository contents.
5. Run the workflow manually twice and inspect the baseline and unchanged second run.

The example workflow deliberately has no schedule. Add a cron trigger only after the private
manual runs are approved.

The first successful scan creates a baseline and sends no change alert.
