# Private Web R2 staging on EC2

This package runs the account-enabled web app, API, worker, PostgreSQL and SMTP capture on the existing Linux ARM64 Docker Compose host. The [R2 requirements](../requirements/backend-release-specification.md) and [ADR-0002](../architecture/decisions/0002-optional-account-backend.md) define the release gates. This runbook covers a private staging deployment with synthetic data. Production ingress, public email and recovery each have separate acceptance checks.

## Build and identify a package

From a clean, reviewed checkout, use the repository's pinned Node and pnpm versions. Run the source and container checks before making an archive for deployment:

```sh
pnpm check
pnpm test:e2e
python3 tools/package-staging.py .local/releases/aion-staging.tar.gz
```

The packaging script uses the frozen lockfile, builds the account-enabled UI with reminders disabled, and exports the Linux ARM64 web and backend images. The backend image is shared by the API, worker and migration job. The manifest records the Git revision, exact local Docker image IDs and image archive SHA-256. The script prints the complete package SHA-256 for the handoff. Pass that checksum separately from the archive and deploy the tested bytes. This path uses a local image archive and Docker image IDs. The pinned PostgreSQL and Mailpit images are pulled by digest.

Backend tests require a disposable local PostgreSQL database. Follow [backend development setup](../development/backend-setup.md) for that separate test database. A staged database is for the staging smoke and recovery rehearsal.

## Install on the shared host

The deployment assumes an approved SSH-free Systems Manager access path, Docker with the Compose plugin, Python 3.11 or newer, OpenSSL and an existing encrypted host volume. Check that loopback ports 28443 and 28025 are available and that the private Docker subnet `172.30.241.0/29` does not overlap a host route or another project. The web container uses `172.30.241.2` on an internal network shared only with the API. Uvicorn trusts forwarding headers from that address. The TLS listener replaces any client-provided chain with the actual immediate peer address.

Keep the archive and extracted files under a release directory dedicated to Aion. Keep the staging state directory separate from the release, under a root-owned project directory. Use the same persistent state path for reinstalls and rollbacks. Stage the package with the operator's approved transfer method, for example a short-lived private S3 transfer with TLS and a verified checksum. Host credentials are generated on the host. The package contains no mail provider key or database credential.

From the extracted `aion-staging` directory on the authorized staging host:

```sh
# Compare the output with the separately recorded package SHA-256 before extracting.
# sha256sum /path/to/aion-staging.tar.gz
sudo AION_STAGING_STATE_DIR=/opt/aion-staging/state sh deploy.sh --check
sudo AION_STAGING_STATE_DIR=/opt/aion-staging/state sh deploy.sh
```

The installer verifies the archive and ARM64 image identities, creates the private state and starts only the `aion-staging` project. Its Postgres volume persists across container replacement. New database initialization creates separate migrator and runtime roles. The migration job applies Alembic and explicit runtime table grants transactionally. The API and worker use the runtime role, which can read the revision and operate on listed tables. Schema ownership and modifications stay with the migrator. A volume created for local development uses a different role layout. Use a fresh staging volume for the first deployment.

Staging publishes HTTPS on `127.0.0.1:28443` and Mailpit's inbox on `127.0.0.1:28025`. The API, database and SMTP listener use private Docker networks. The account origin is exactly `https://127.0.0.1:28443`. The `localhost` alias redirects there. The generated certificate is for private staging and expires after 30 days. Inspect its SHA-256 fingerprint over Systems Manager and trust only that certificate for this endpoint. Use the Session Manager local port forwarding document to forward the two ports to matching local ports when running browser checks. See [AWS Session Manager port forwarding](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-sessions-start.html#sessions-start-port-forwarding).

## Verify the deployed artifact

- Check Compose status and verify the running API and worker image IDs match the manifest. Verify `/version.json` reports the recorded source revision and `dirty: false`.
- From the tunnel verify `/`, `/es` and an account route. Request `/api/v1/health/ready`, an unknown API route and `/api`. Expect JSON `200`, `404` and `404`, with `Cache-Control: no-store`. Check same-origin CSP. API unavailability should return JSON `503` while the guest UI remains usable.
- Use synthetic `@example.test` addresses and the tunneled inbox to verify account creation, login, profile import, sync, confirmation and sign-out. Verify account navigation works in English and Spanish. Check that reminder enrollment is hidden. Run the browser journeys from [account development setup](../development/account-setup.md) with `AION_AUTH_TESTS=1`, `AION_DEFERRED_REMINDER_UI=1`, `AION_BASE_URL=https://127.0.0.1:28443` and `AION_INBOX_URL=http://127.0.0.1:28025`.
- Verify edge header handling and the per-IP limit with synthetic login requests. Forged forwarding headers must leave requests in the same budget. Keep codes, cookies and temporary data out of traces, request logs and command output.
- Check API readiness, worker heartbeat, disk use and container log rotation. Record the elapsed deployment time and resources observed. Physical iPhone, Safari, VoiceOver, production load and alert delivery require separate evidence.

## Recover or promote

To stop staging during investigation, run `docker compose -p aion-staging --env-file images.env stop` from its extracted release directory with `AION_STAGING_STATE_DIR` set. Preserve the database volume, state files and reviewed package. For an application rollback, select a previous verified package compatible with the current database revision. Check the migration target and stop the worker if investigating queued delivery. For an incompatible database, keep account service in maintenance while following a rehearsed restore procedure. The [R1 static rollback](web-deployment.md) is available only for the guest site.

Before public accounts, rehearse encrypted off-instance database and key restore, deletion and suppression reconciliation, and session/code/job invalidation. Verify the production TLS and trusted Cloudflare-to-Caddy client address boundary, cache bypass, monitoring and rollback. Verify transactional Resend delivery and signature-verified callbacks under the separately authorized rollout. Private staging uses the capture inbox. It therefore needs neither public DNS nor a route on the shared Caddy proxy.
