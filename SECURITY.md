# Security

Aion 0.1.x is an early web release. Security fixes target the latest published revision; there is no response-time guarantee or older-version support commitment.

Report sensitive vulnerabilities through [GitHub private vulnerability reporting](https://github.com/agapeengineering/aion/security/advisories/new). Public issues are appropriate for non-sensitive bugs and suggestions. Do not include personal birth dates, credentials or private exported settings in public reports.

Aion stores versioned settings only in browser local storage, without a backend, account, analytics SDK or cloud sync. It does not transmit personal inputs in URLs, requests or diagnostic logs. Cloudflare serves static assets and can process standard connection/request information under its policies. Content Security Policy restricts scripts/fonts to the site and disables application network connections; local PNG previews use blob URLs.

Local storage is browser-specific and is not a backup. Clearing/resetting it requires re-entering the two inputs; downloaded wallpapers remain on the device until separately removed. Unsupported/newer or malformed settings are protected from silent overwrite until explicit reset.
