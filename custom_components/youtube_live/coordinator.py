"""DataUpdateCoordinators for the YouTube Live integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
import logging
from typing import TYPE_CHECKING

from yt_live_scraper import StreamLiveStatus, UpcomingStream, get_upcoming_streams, is_stream_live

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    ACTIVE_WINDOW_MINUTES,
    CONF_CHANNEL_HANDLE,
    DEFAULT_CALENDAR_INTERVAL,
    DEFAULT_SENSOR_INTERVAL,
    DOMAIN,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)


@dataclass
class StreamStatus:
    """Track the polling state of a single stream."""

    is_live: bool = False
    was_live: bool = False
    ended: bool = False


class CalendarCoordinator(DataUpdateCoordinator[list[UpcomingStream]]):
    """Coordinator that fetches upcoming streams hourly."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the calendar coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_calendar",
            config_entry=config_entry,
            update_interval=DEFAULT_CALENDAR_INTERVAL,
        )
        self.channel_handle: str = config_entry.data[CONF_CHANNEL_HANDLE]

    async def _async_update_data(self) -> list[UpcomingStream]:
        """Fetch upcoming streams from YouTube."""
        _LOGGER.debug(
            "Fetching upcoming streams for %s", self.channel_handle
        )
        try:
            streams: list[UpcomingStream] = await self.hass.async_add_executor_job(
                get_upcoming_streams, [self.channel_handle]
            )
        except Exception as err:
            _LOGGER.error(
                "Error fetching streams for %s: %s", self.channel_handle, err, exc_info=True
            )
            raise UpdateFailed(
                f"Error fetching streams for {self.channel_handle}: {err}"
            ) from err
        _LOGGER.debug(
            "Found %d upcoming stream(s) for %s: %s",
            len(streams),
            self.channel_handle,
            [f"{s.video_id} ({s.title})" for s in streams],
        )
        return streams


@dataclass
class StreamStatusData:
    """Data returned by the stream status coordinator."""

    statuses: dict[str, StreamStatus] = field(default_factory=dict)


class StreamStatusCoordinator(DataUpdateCoordinator[StreamStatusData]):
    """Coordinator that polls live status for streams in the active window."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        calendar_coordinator: CalendarCoordinator,
    ) -> None:
        """Initialize the stream status coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_stream_status",
            config_entry=config_entry,
            update_interval=DEFAULT_SENSOR_INTERVAL,
        )
        self.calendar_coordinator = calendar_coordinator
        self._stream_states: dict[str, StreamStatus] = {}

    def _is_in_active_window(self, stream: UpcomingStream) -> bool:
        """Check if a stream is in the active polling window."""
        now = dt_util.utcnow()
        window_start = stream.scheduled_start - timedelta(minutes=ACTIVE_WINDOW_MINUTES)
        window_end = stream.scheduled_start + timedelta(minutes=ACTIVE_WINDOW_MINUTES)

        video_id = stream.video_id
        state = self._stream_states.get(video_id)

        if state and state.ended:
            return False

        if state and state.was_live:
            # Keep polling until the stream ends
            return True

        return window_start <= now <= window_end

    async def _async_update_data(self) -> StreamStatusData:
        """Poll live status for streams in the active window."""
        streams = self.calendar_coordinator.data or []
        now = dt_util.utcnow()

        _LOGGER.debug(
            "StreamStatusCoordinator updating. Current calendar data has %d streams: %s",
            len(streams),
            [s.video_id for s in streams],
        )

        # Clean up states for streams no longer in calendar data
        known_ids = {s.video_id for s in streams}
        removed = set(self._stream_states) - known_ids
        if removed:
            _LOGGER.debug(
                "Removing stale stream states: %s", removed
            )
        self._stream_states = {
            vid: state
            for vid, state in self._stream_states.items()
            if vid in known_ids
        }

        for stream in streams:
            video_id = stream.video_id
            state = self._stream_states.get(video_id)
            if state and state.is_live:
                # Keep polling if currently live
                _LOGGER.debug("Stream %s is live, continuing to poll", video_id)
                pass
            elif stream.live:
                # If the scraper already says it's live, we should poll it
                _LOGGER.debug("Stream %s is marked as live by scraper, starting polling", video_id)
                pass
            elif not self._is_in_active_window(stream):
                _LOGGER.debug("Stream %s is outside active window, skipping", video_id)
                continue

            if video_id not in self._stream_states:
                _LOGGER.debug(
                    "Stream %s (%s) entered active window, starting polling",
                    video_id,
                    stream.title,
                )
                self._stream_states[video_id] = StreamStatus()

            state = self._stream_states[video_id]

            if state.ended:
                _LOGGER.debug("Stream %s has already ended, skipping poll", video_id)
                continue

            try:
                _LOGGER.debug("Polling live status for stream %s", video_id)
                result: StreamLiveStatus = await self.hass.async_add_executor_job(
                    is_stream_live, video_id
                )
            except Exception:
                _LOGGER.debug(
                    "Error checking live status for %s", video_id, exc_info=True
                )
                continue

            live = result.is_live

            # Correct the scheduled_start when the player response
            # provides the actual broadcast start time.  This fixes the
            # calendar showing "now" instead of the original time after
            # a Home Assistant restart while a stream is already live.
            if result.actual_start is not None:
                if stream.scheduled_start != result.actual_start:
                    _LOGGER.debug(
                        "Correcting scheduled_start for %s from %s to %s",
                        video_id,
                        stream.scheduled_start,
                        result.actual_start,
                    )
                    stream.scheduled_start = result.actual_start

            state.is_live = live

            _LOGGER.debug(
                "Stream %s poll result: is_live=%s, actual_start=%s",
                video_id,
                live,
                result.actual_start,
            )

            if live and not state.was_live:
                _LOGGER.info(
                    "Stream %s (%s) is now live", video_id, stream.title
                )
                state.was_live = True
            elif live:
                state.was_live = True
            elif state.was_live:
                # Stream was live but is no longer — it ended
                _LOGGER.info(
                    "Stream %s (%s) has ended", video_id, stream.title
                )
                state.is_live = False
                state.ended = True
            elif now > stream.scheduled_start + timedelta(minutes=ACTIVE_WINDOW_MINUTES):
                # Past the active window and never went live
                _LOGGER.debug(
                    "Stream %s (%s) passed active window without going live",
                    video_id,
                    stream.title,
                )
                state.ended = True

        _LOGGER.debug(
            "StreamStatusCoordinator update finished. Current states: %s",
            {vid: f"live={s.is_live}, ended={s.ended}" for vid, s in self._stream_states.items()},
        )
        return StreamStatusData(statuses=dict(self._stream_states))
