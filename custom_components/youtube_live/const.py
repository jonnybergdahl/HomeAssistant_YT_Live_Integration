"""Constants for the YouTube Live integration."""

from datetime import timedelta

DOMAIN = "youtube_live"

CONF_CHANNEL_HANDLE = "channel_handle"

DEFAULT_CALENDAR_INTERVAL = timedelta(hours=1)
DEFAULT_SENSOR_INTERVAL = timedelta(minutes=1)
ACTIVE_WINDOW_MINUTES = 15
DEFAULT_STREAM_DURATION_HOURS = 2
