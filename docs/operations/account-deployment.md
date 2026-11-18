# Account service deployment and recovery

Use the same reviewed ARM64 image archive for rehearsal and promotion. Verify the archive checksum, the manifest's image identifiers and the source revision served at `/version.json`. The account service requires its own Compose project, private state directory, database volume, recovery journal epoch and off-host storage prefixes. Keep the guest Worker attached until the release owner approves promotion.

## Prepare the private origin

Extract the package and load its verified images. Generate the production state with the packaged `prepare-state.py`. Provision the following additional files beneath the mode-0700 state directory.

| File | Use |
| --- | --- |
| `journal-epoch` | Independent production baseline and recovery timeline |
| `mail.env` | Sender, Reply-To, allowlist and positive daily provider attempt budget |
| `resend-worker-key` | Domain-scoped sending credential, mounted only in the worker |
| `resend-webhook-secret` | Signing key issued for the permanent transactional callback |
| `origin-recovery.tar.gz` | Operator-owned proxy, connector, monitoring and recovery configuration needed to reconstruct this service |

The web and API have no published host ports. Connect only the shared origin proxy to the project's private frontend at `172.30.244.3`. It routes `/api` and `/api/*` to the API at `172.30.244.4:8000` and other paths to the static server at `172.30.244.2:8080`. Restrict the origin listener to the authenticated edge connection. Establish a new forwarding chain using the client address supplied by that connection. The API trusts only the proxy address. Return JSON and `Cache-Control: no-store` for all API responses, including failures. Cache only identified immutable assets.

Set `AION_STAGING_STATE_DIR` to the **production** state directory and `AION_PRODUCTION_JOURNAL_DIR` to the production relay directory. The shared state variable name is retained for compatibility with the packaged bootstrap. Use the complete model for every production service change:

```sh
docker compose -p aion-production --env-file images.env \
  -f compose.yaml -f compose.journal.yaml -f compose.production.yaml config --quiet
docker compose -p aion-production --env-file images.env \
  -f compose.yaml -f compose.journal.yaml -f compose.production.yaml up -d --no-build --wait
```

Before starting writers, initialize the schema and freeze writes while capturing the empty baseline. Use the production relay flag and verify the baseline under `markers/production/journal/<epoch>/` from the separate operator identity. External account access stays gated during rehearsal. For a browser rehearsal on a different hostname, set `AION_ACCOUNT_ORIGIN` to that exact HTTPS origin in allowlisted mode. Restore the canonical origin for promotion. The application rejects public mail on any other origin. In the allowlisted configuration, use the approved test recipients only. For public sending, install an empty recipient allowlist and explicitly set `AION_PUBLIC_MAIL=true` at the approved cutover. Scheduled reminders stay disabled.

## Verify and promote

Exercise private HTTPS and the candidate edge hostname. Check API readiness and unknown-route JSON, cache headers, trusted client identity, duplicate and unsigned callback handling, cookie/CSRF behavior, guest access, and browser sign-in and account lifecycle. Use synthetic data for load tests and a capture mail transport in an isolated environment. Confirm both public API cache bypass and direct-origin access controls. Test alert receipt, backup age, worker heartbeat and queue health. Record the original guest Worker attachment and deployment along with the candidate artifact, previous compatible revision and the named origin route.

At the approved switch, verify a fresh backup, enable the reviewed canonical route and repeat the release checks at the public hostname. Keep a maintenance route that disables account writes and mail while serving the guest experience. A compatible image rollback preserves the PostgreSQL volume and recovery epoch. Verify the schema and release identity before reopening writes.

## Recover on a new host

Set `AION_RECOVERY_SOURCE_PROJECT=aion-production` in the production backup environment. The ordinary snapshot, key and periodic marker objects are under `snapshots/production/`, `keys/production/` and `markers/production/`. Run the independent collector with `--production` and the fenced source cutoff. Use the operator-held decryption key and the archived data, configuration and checksums as described in [backend recovery](backend-recovery.md). The database-only restore validates the production epoch, reconciles deletions and suppressions, and invalidates stale authentication and jobs before traffic.

The encrypted production bundle includes the epoch, provider credentials and the origin recovery archive. Inspect the restored configuration in an owner-private directory. Recreate the proxy and connector trust, provision the production relay, and independently verify the new writer's epoch before serving accounts. Validate a signed callback, source address handling and scheduled monitoring. If trusted provider or connector credentials cannot be recovered, rotate and test replacements before enabling their consumers.
