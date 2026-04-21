"""DataUpdateCoordinators for the YouTube Live integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
import logging
from typing import TYPE_CHECKING

from yt_live_scraper import StreamLiveStatus, UpcomingStream, get_upcoming_streams, is_stream_live
from yt_live_scraper.scraper import get_channel_info

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    ACTIVE_WINDOW_MINUTES,
    CONF_CHANNEL_HANDLES,
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
    """Coordinator that fetches upcoming streams hourly for a channel group."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the calendar coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_calendar_{config_entry.entry_id}",
            config_entry=config_entry,
            update_interval=DEFAULT_CALENDAR_INTERVAL,
        )
        self.channel_handles: list[str] = list(
            config_entry.data.get(CONF_CHANNEL_HANDLES, [])
        )
        # handle (lowercased, with @) -> avatar URL; used as entity_picture
        # fallback for per-channel binary sensors that don't have a current
        # or upcoming stream.
        self.channel_thumbnail_urls: dict[str, str] = {}
        # handle (lowercased, with @) -> display name
        self.channel_names: dict[str, str] = {}

    @staticmethod
    def _hkey(handle: str) -> str:
        """Canonical key for matching handles."""
        h = handle.strip()
        if not h.startswith("@"):
            h = f"@{h}"
        return h.lower()

    async def _async_update_data(self) -> list[UpcomingStream]:
        """Fetch upcoming streams from YouTube for every channel in the group."""
        # Update our list of handles from the config entry
        self.channel_handles = list(
            self.config_entry.data.get(CONF_CHANNEL_HANDLES, [])
        )
        # Cleanup stale metadata for channels that were removed
        current_keys = {self._hkey(h) for h in self.channel_handles}
        self.channel_thumbnail_urls = {
            k: v for k, v in self.channel_thumbnail_urls.items() if k in current_keys
        }
        self.channel_names = {
            k: v for k, v in self.channel_names.items() if k in current_keys
        }

        _LOGGER.debug(
            "Fetching upcoming streams for group %s (%d channels)",
            self.config_entry.title,
            len(self.channel_handles),
        )
        try:
            streams: list[UpcomingStream] = await self.hass.async_add_executor_job(
                get_upcoming_streams, self.channel_handles
            )
        except Exception as err:
            _LOGGER.error(
                "Error fetching streams for group %s: %s",
                self.config_entry.title,
                err,
                exc_info=True,
            )
            raise UpdateFailed(
                f"Error fetching streams for group {self.config_entry.title}: {err}"
            ) from err

        _LOGGER.debug(
            "Group %s: found %d stream(s): %s",
            self.config_entry.title,
            len(streams),
            [f"{s.video_id} ({s.title})" for s in streams],
        )

        # Populate channel thumbnails/names from the streams we already fetched.
        seen_channel_ids: dict[str, str] = {}
        for stream in streams:
            if stream.channel_thumbnail_url and stream.channel_id:
                seen_channel_ids[stream.channel_id] = stream.channel_thumbnail_url

        # Map channel_id -> handle key from our configured list when we can,
        # otherwise fall back to get_channel_info.
        for handle in self.channel_handles:
            key = self._hkey(handle)
            if key in self.channel_thumbnail_urls and key in self.channel_names:
                continue
            matched = False
            for stream in streams:
                if stream.channel.lower() == handle.lstrip("@").lower() or (
                    stream.channel_id
                    and stream.channel_id == self.channel_names.get(key)
                ):
                    # We only have display name or id to match on; store what we have.
                    if stream.channel_thumbnail_url:
                        self.channel_thumbnail_urls[key] = stream.channel_thumbnail_url
                    if stream.channel:
                        self.channel_names[key] = stream.channel
                    matched = True
                    break
            if matched:
                continue
            # No stream for this handle — fetch channel info directly.
            try:
                info = await self.hass.async_add_executor_job(
                    get_channel_info, handle
                )
            except Exception as err:
                _LOGGER.debug(
                    "Could not fetch channel info for %s: %s", handle, err
                )
                info = None
            if info is not None:
                self.channel_names[key] = info.name
                if info.thumbnail_url:
                    self.channel_thumbnail_urls[key] = info.thumbnail_url

        return streams

    def streams_for_handle(self, handle: str) -> list[UpcomingStream]:
        """Return the streams that belong to a specific handle.

        Streams returned by the scraper expose ``channel`` (display name) and
        ``channel_id`` but not the handle; we match case-insensitively on the
        display name stored in :attr:`channel_names`, falling back to
        comparing the handle-without-@ to the channel display name.
        """
        if not self.data:
            return []
        key = self._hkey(handle)
        display_name = self.channel_names.get(key)
        bare = handle.lstrip("@").lower()
        out: list[UpcomingStream] = []
        for stream in self.data:
            name = (stream.channel or "").lower()
            if display_name and name == display_name.lower():
                out.append(stream)
            elif name == bare:
                out.append(stream)
        return out


@dataclass
class StreamStatusData:
    """Data returned by the stream status coordinator."""

    statuses: dict[str, StreamStatus] = field(default_factory=dict)


@dataclass
class StreamMetadata:
    """Store metadata for a stream being tracked."""

    handle: str
    stream: UpcomingStream


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
            name=f"{DOMAIN}_stream_status_{config_entry.entry_id}",
            config_entry=config_entry,
            update_interval=DEFAULT_SENSOR_INTERVAL,
        )
        self.calendar_coordinator = calendar_coordinator
        self._stream_states: dict[str, StreamStatus] = {}
        # video_id -> StreamMetadata
        self.stream_metadata: dict[str, StreamMetadata] = {}

    def _get_stream_handle(self, stream: UpcomingStream) -> str | None:
        """Find the handle associated with a stream."""
        calendar = self.calendar_coordinator
        for handle in calendar.channel_handles:
            key = calendar._hkey(handle)
            display_name = calendar.channel_names.get(key)
            bare = handle.lstrip("@").lower()
            name = (stream.channel or "").lower()
            if (display_name and name == display_name.lower()) or name == bare:
                return handle
        return None

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

        # Clean up states for streams no longer in calendar data,
        # unless they are currently live.
        known_ids = {s.video_id for s in streams}
        removed = set(self._stream_states) - (known_ids | {vid for vid, state in self._stream_states.items() if state.is_live})
        if removed:
            _LOGGER.debug(
                "Removing stale stream states: %s", removed
            )
        self._stream_states = {
            vid: state
            for vid, state in self._stream_states.items()
            if vid in known_ids or state.is_live
        }
        self.stream_metadata = {
            vid: meta
            for vid, meta in self.stream_metadata.items()
            if vid in self._stream_states
        }

        # Add new streams from calendar to states
        for stream in streams:
            if stream.video_id not in self._stream_states:
                if self._is_in_active_window(stream):
                    _LOGGER.debug(
                        "Stream %s (%s) entered active window, starting polling",
                        stream.video_id,
                        stream.title,
                    )
                    self._stream_states[stream.video_id] = StreamStatus()
                elif stream.live:
                     _LOGGER.debug("Stream %s is marked as live by scraper, starting polling", stream.video_id)
                     self._stream_states[stream.video_id] = StreamStatus()
            
            # Update metadata if we have it
            if stream.video_id in self._stream_states and stream.video_id not in self.stream_metadata:
                if handle := self._get_stream_handle(stream):
                    self.stream_metadata[stream.video_id] = StreamMetadata(handle, stream)

        # Poll all streams currently in states (includes those from calendar
        # and those that were already live but dropped from calendar).
        for video_id, state in list(self._stream_states.items()):
            # Find the stream object from calendar data if available
            stream = next((s for s in streams if s.video_id == video_id), None)

            if state.is_live:
                # Keep polling if currently live
                _LOGGER.debug("Stream %s is live, continuing to poll", video_id)
                pass
            elif stream and stream.live:
                # If the scraper already says it's live, we should poll it
                _LOGGER.debug("Stream %s is marked as live by scraper, starting polling", video_id)
                # If it was marked as ended, reset it so we can poll again
                state.ended = False
                pass
            elif stream and not self._is_in_active_window(stream):
                _LOGGER.debug("Stream %s is outside active window, skipping", video_id)
                continue
            elif not stream and not state.is_live:
                # Should not really happen due to cleanup above, but for safety:
                # if it's not in calendar and not live, we don't need to poll it.
                continue

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

            # Correct the scheduled_start when the player response provides
            # the actual broadcast start time. This fixes the calendar showing
            # "now" instead of the original time after a Home Assistant
            # restart while a stream is already live.
            if stream and result.actual_start is not None:
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

            title = stream.title if stream else video_id
            if live and not state.was_live:
                _LOGGER.info(
                    "Stream %s (%s) is now live", video_id, title
                )
                state.was_live = True
            elif live:
                state.was_live = True
            elif state.was_live:
                # Stream was live but is no longer — it ended
                _LOGGER.info(
                    "Stream %s (%s) has ended", video_id, title
                )
                state.is_live = False
                state.ended = True
            elif stream and now > stream.scheduled_start + timedelta(minutes=ACTIVE_WINDOW_MINUTES):
                # Past the active window and never went live
                _LOGGER.debug(
                    "Stream %s (%s) passed active window without going live",
                    video_id,
                    title,
                )
                state.ended = True

        _LOGGER.debug(
            "StreamStatusCoordinator update finished. Current states: %s",
            {vid: f"live={s.is_live}, ended={s.ended}" for vid, s in self._stream_states.items()},
        )
        return StreamStatusData(statuses=dict(self._stream_states))
