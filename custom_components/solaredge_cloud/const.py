"""Constants for SolarEdge Cloud (Monitoring API V2)."""

from datetime import timedelta
import logging

DOMAIN = "solaredge_cloud"
LOGGER = logging.getLogger(__package__)

API_BASE_URL = "https://monitoringapi.solaredge.com/v2"
OAUTH2_AUTHORIZE = "https://connect.solaredge.com/authorize"
OAUTH2_TOKEN = f"{API_BASE_URL}/oauth2/token"
OAUTH2_SCOPE = "SITE_DATA DEVICE_DATA"
CALLBACK_PATH = "/api/solaredge_cloud/callback"

CONF_SITE_ID = "site_id"
CONF_CLIENT_ID = "client_id"
CONF_CLIENT_SECRET = "client_secret"
CONF_TOKEN = "token"

# The free tier gives ~2000 credits per month (≈ 65 per day) and 10 per minute;
# every call costs one credit. The coordinator ticks every 5 minutes but only
# calls an endpoint when its interval has passed: ~55 calls per day in total.
TICK_INTERVAL = timedelta(minutes=5)
DAY_INTERVAL_SUN_UP = timedelta(minutes=30)
DAY_INTERVAL_SUN_DOWN = timedelta(hours=3)
MONTH_INTERVAL = timedelta(hours=3)
YEAR_INTERVAL = timedelta(hours=6)
LIFETIME_INTERVAL = timedelta(hours=6)
DETAILS_INTERVAL = timedelta(hours=24)
ALERTS_INTERVAL = timedelta(hours=3)
BENEFITS_INTERVAL = timedelta(hours=24)
DEVICES_INTERVAL = timedelta(hours=24)
ERROR_BACKOFF = timedelta(minutes=30)
