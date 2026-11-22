# Security policy

## Supported versions

Only the latest release gets fixes. Please update through HACS before reporting.

## Reporting a vulnerability

Please **don't** open a public issue for security problems.

Report it privately instead: go to the
[Security tab](https://github.com/rvdwal1991/solaredge-v2-ha/security) and click
**Report a vulnerability**. Only the maintainer can see the report.

Include what you found, how to reproduce it and which version you use. **Never include
your Client secret, tokens or other credentials**, also not in logs or diagnostics.

This is a hobby project, so there is no fixed response time. Expect a first reply
within about a week.

## What this integration stores

- The SolarEdge Client ID, Client secret and OAuth tokens are stored in Home Assistant's
  config entry (`.storage/core.config_entries`), like every other integration.
- Diagnostics leave out the secret, the tokens, the site location and serial numbers.
- The OAuth callback (`/api/solaredge_cloud/callback`) only accepts a response for a setup
  flow that is in progress, and uses PKCE.
