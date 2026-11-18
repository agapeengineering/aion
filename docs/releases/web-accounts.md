# Optional web accounts

Released on 18 November 2026 at [aion.agape.engineering](https://aion.agape.engineering). The web and backend images were built from commit `9ec5d37d2125523f72ecbfec2c4d3028af18a385`. The public [build identifier](https://aion.agape.engineering/version.json) reports the web source revision.

## What shipped

The English and Spanish calendar works as a guest. Existing browser calendars survive the upgrade. An email code lets a person create or access an account. Saving a calendar to an account enables cross-device sync. Importing an existing guest calendar requires an explicit choice. Account settings include session controls, data export and permanent deletion. Scheduled email reflections are deferred.

## What was verified

- A browser saved a guest calendar on the previous release and reopened it on the new release with the same settings. Guest use made zero account API requests. Chromium, Firefox and WebKit also rendered the calendar, wallpaper and both sign-in languages.
- A test mailbox received a sign-in code and a separate account-confirmation code. A browser used them on the public site to sign in, save and reload a profile, download its data and delete the account. The server then rejected the old session. Both email deliveries produced signed provider callbacks.
- Two separate test accounts retrieved only their own profiles. The public API rejected mismatched account identifiers and writes without valid CSRF protection. The API returned uncached JSON during normal service and during the deployment maintenance window.
- The production restore rehearsal retained two independent profiles, excluded a deleted account and revoked old sessions. At launch, an independent read verified the off-instance deletion record for the test account. The operator also verified the off-instance database backup and decrypted the recovery configuration.

For ongoing operation, use the account deployment and database recovery procedures. Historical browser and physical-device verification limits are recorded separately. [Account deployment](../operations/account-deployment.md) · [Database recovery](../operations/backend-recovery.md) · [Web verification](../testing/web-verification.md)
