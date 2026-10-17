# Web deployment, rollback and recovery

Maintainer: Agape Engineering. Channel: early web 0.1.x. Static assets only; there is no server-side user database or personal-data backup.

## Deploy

1. Verify correct repository, clean intended source revision, Node/pnpm versions and the Cloudflare identity with `pnpm exec wrangler whoami`. Do not print or commit OAuth/API credentials.
2. From a clean checkout run `pnpm install --frozen-lockfile`, `pnpm check`, `pnpm test:e2e`, and `pnpm audit --prod`. Review public source, dependency notices and deployment authorization.
3. Run `pnpm deploy:dry`; check `apps/web/dist/version.json` records the intended revision with `dirty:false`.
4. Run `pnpm deploy:staging`, record the Worker version ID, and run `AION_BASE_URL=https://aion-staging.jorgesandev.workers.dev pnpm test:e2e`. Verify EN/ES, headers and source metadata. This only uses synthetic local browser data.
5. Promote the **same unchanged built directory** using `pnpm deploy`. This deploys the production environment and custom domain `aion.agape.engineering`. Do not rebuild between stage and production promotion.
6. Verify HTTPS, `/`, `/es`, `/version.json`, setup/edit/reload/reset, hidden-figure PNG export and privacy/network behavior at the actual URL. Record artifact/source revision, deployment version and known limitations in the release record.

The initial production release has no previous production Aion version. If no safe previous version exists, contain/repair rather than claiming an available rollback target. Do not edit unrelated services/domains to recover this app.

## Rollback

Inspect `pnpm exec wrangler versions list --env production` and `pnpm exec wrangler deployments list --env production` and select an actual previously verified compatible version. Stop if the target identity or expected effect is unclear. Within existing recovery authorization, run `pnpm exec wrangler rollback <verified-version-id> --env production --message '<reason>' --yes`. Placeholder text is documentation, not an executable recovery command.

Then verify HTTPS, source metadata and the core flow again. The equivalent staging command uses `--env staging`; rehearse there before claiming rollback readiness. Record the actual version IDs and observed restored artifact in the release evidence. Local settings remain client-owned and must stay backward-compatible; never silently overwrite a newer schema to make rollback appear successful.

## Rebuild and data recovery

Restore source from the recorded Git commit, install from the lockfile in a fresh directory, run checks/build and compare the version metadata and asset hashes. Keep a record of accepted configuration changes. Redeploy only under the appropriate authority. There are no host volumes, database migrations or private user records to restore.

Browser settings cannot be recovered from the server. Users re-enter their birth date/horizon after reset, browser clearing or changing devices. Wallpaper images remain on their device. Support must not request private settings in public issues.

## Observation and maintenance

Check the public core flow after every release, review reported defects and health regularly, and review dependencies/Cloudflare costs/access monthly. Platform dashboards and GitHub CI provide deployment/check evidence. Independent uptime alerting is not configured by this release; do not promise 24/7 monitoring or response. Sensitive security reports use GitHub private reporting. No automatic spending or paid-service upgrade is authorized by these steps.
