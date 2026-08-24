# GitHub release handoff

Publish only after every local check in `BUILD_STATUS.md` is green.

1. Create `marmarmar-code/website-investigator` as public and the companion runtime repository as
   private. Verify both visibilities through the GitHub API.
2. Push the public `main` branch and wait for CI to pass.
3. Tag the validated public commit `v0.1.0`. The release workflow publishes only that tag to GHCR.
4. Read the immutable `sha256` digest from the completed release workflow, make the package public,
   and prove an anonymous pull using `image@sha256:digest`.
5. Put that exact image, version and digest in the private `engine.lock`; never use `latest`.
6. Keep the private workflow dispatch-only. Run it twice with the harmless example target, verify
   the baseline and the unchanged second run, then remove the active example target.

Do not add a schedule or real targets until the private manual run has been reviewed and separately
approved.
