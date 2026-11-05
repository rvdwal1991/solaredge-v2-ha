# SolarEdge Cloud (API v2) for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories)
[![Validate](https://github.com/rvdwal1991/solaredge-v2-ha/actions/workflows/validate.yml/badge.svg)](https://github.com/rvdwal1991/solaredge-v2-ha/actions/workflows/validate.yml)

SolarEdge retired its V1 Monitoring API on **3 November 2026**. Since then the built-in
Home Assistant `solaredge` integration fails with `410 Gone` / *API Version Deprecated*,
and old API keys no longer work. This custom integration uses the new
**SolarEdge Monitoring API V2** with OAuth2, so you get your production data back.

## Features

| Entity | Description | Refreshed |
|---|---|---|
| Energy today | Production today (kWh) | every 30 min while the sun is up, every 3 h at night |
| Energy this month / this year | Production totals (kWh) | every 3 h / 6 h |
| Lifetime energy | Total production (kWh) | every 6 h |
| Specific yield today / this month | kWh per installed kWp | calculated, no extra calls |
| Open alerts + **Problem** binary sensor | Open SolarEdge alerts (type, component, error codes as attributes) | every 3 h |
| CO₂ avoided | Lifetime CO₂ avoided (kg), equivalent EV km as attribute | daily |
| Optimizers | Number of optimizers, inverter model and firmware as attributes | daily |
| Site status, last SolarEdge update | Diagnostic | daily / with every update |

The device page also shows the inverter model and firmware version.
All energy sensors use `total_increasing`, so they work in the Energy dashboard.

### API credits

The free SolarEdge tier gives about **2,000 API calls per month** and 10 per minute.
This integration uses about **55 calls per day (~1,650 per month)**. It backs off for
30 minutes after an error and keeps showing the last known values.

> Tip: for live power (watts, every few seconds) use the local
> [SolarEdge Modbus](https://github.com/WillCodeForCats/solaredge-modbus-multi) integration
> next to this one. The cloud API is only refreshed every 15 minutes or so.

## Requirements

- Home Assistant **2025.3** or newer (2026.3+ shows the SolarEdge logo).
- Home Assistant must be reachable over **https** on its external URL, for example through
  Home Assistant Cloud (Nabu Casa) or your own reverse proxy. SolarEdge only redirects to
  https addresses (or `localhost`).
- The account that owns the SolarEdge site (the one you use in the mySolarEdge app or
  the monitoring portal).

## Installation

### HACS (recommended)

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=rvdwal1991&repository=solaredge-v2-ha&category=integration)

1. Click the button above. If that doesn't work: HACS → ⋮ → **Custom repositories** →
   add `https://github.com/rvdwal1991/solaredge-v2-ha`, category **Integration**.
2. Click **Download** for **SolarEdge Cloud (API v2)**.
3. Restart Home Assistant.

### Manual

Copy `custom_components/solaredge_cloud` into the `custom_components` folder of your
Home Assistant configuration and restart.

## Setup

### 1. Create a SolarEdge application

1. Sign in at [developer.solaredge.com](https://developer.solaredge.com/) and create an
   application.
2. Access type: **Site Access**. Scopes: tick both **SITE_DATA** and **DEVICE_DATA**.
3. Under **Allowed Redirect URL(s)** add:

   ```
   https://<your-home-assistant-address>/api/solaredge_cloud/callback
   ```

   Use your external URL with no slash at the end. The setup form in Home Assistant
   shows the exact URL to copy. Leave *Origin URL* and *Returned URL* empty.
4. Submit and save the **Client ID** and **Client secret**. The secret is only shown once.

### 2. Add the integration

[![Open your Home Assistant instance and start setting up SolarEdge Cloud.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=solaredge_cloud)

1. Click the button above, or go to **Settings → Devices & services → Add integration →
   SolarEdge Cloud (API v2)**.
2. Enter your **Site ID** (in the monitoring portal or app under site details), the
   Client ID and the Client secret.
3. A SolarEdge window opens. Sign in with the **site owner's** account and grant access.
4. The window says *Done* and closes. The integration is set up.

If SolarEdge ever revokes the access, Home Assistant asks you to re-authenticate and
you go through step 3 again.

## Migrating from the built-in SolarEdge integration

The built-in integration keeps failing with `410 Gone`. After setting this one up:

1. Remove the old **SolarEdge** integration.
2. Point dashboard cards and the Energy dashboard to the new
   `sensor.solaredge_site_<site_id>_*` entities.

The long-term statistics of the old sensors stay in your history.

## Troubleshooting

- **"Authorization failed: … invalid_client"**: the Client ID or secret is wrong.
- **The SolarEdge window shows a redirect error**: the redirect URL registered at
  SolarEdge must match the one shown in the setup form exactly.
- **"We couldn't verify your account"**: sign in with the account that owns the site,
  not just the developer account.
- **Diagnostics**: on the integration page, *Download diagnostics* shows the raw API
  responses and the rate-limit headers. Secrets, location and serial numbers are left out.

## Not supported

- Per-panel / per-optimizer production. This is only in SolarEdge's paid Advanced
  Monitoring API.
- Grid import/export, consumption and battery data are available from the API but not
  exposed yet (pull requests welcome). The author's site has no SolarEdge meter or
  battery to test with.

## License

Apache License 2.0, see [LICENSE](LICENSE) and [NOTICE](NOTICE).
This project is not affiliated with or endorsed by SolarEdge.
