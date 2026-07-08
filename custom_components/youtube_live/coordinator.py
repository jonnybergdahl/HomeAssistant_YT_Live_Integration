"""DataUpdateCoordinator for the YouTube Live integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
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
    DEFAULT_STREAM_DURATION_HOURS,
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
    # UTC time at which the stream was first observed to have ended after being
    # live. ``None`` when the stream never went live or is still ongoing.
    ended_at: datetime | None = None


@dataclass
class YouTubeLiveCoordinatorData:
    """Data maintained by the YouTube Live coordinator."""

    streams: list[UpcomingStream] = field(default_factory=list)
    statuses: dict[str, StreamStatus] = field(default_factory=dict)
    # video_id -> original UpcomingStream object, used when a stream drops from the scraper but is still live
    stream_metadata: dict[str, UpcomingStream] = field(default_factory=dict)


class YouTubeLiveCoordinator(DataUpdateCoordinator[YouTubeLiveCoordinatorData]):
    """Coordinator that manages both upcoming streams and their live status."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{config_entry.entry_id}",
            config_entry=config_entry,
            update_interval=DEFAULT_SENSOR_INTERVAL,
        )
        self.channel_handles: list[str] = list(
            config_entry.data.get(CONF_CHANNEL_HANDLES, [])
        )
        # handle (lowercased, with @) -> avatar URL
        self.channel_thumbnail_urls: dict[str, str] = {}
        # handle (lowercased, with @) -> display name
        self.channel_names: dict[str, str] = {}
        # handle (lowercased, with @) -> channel ID
        self.channel_ids: dict[str, str] = {}

        self._last_calendar_update: datetime | None = None
        # Working state, mutated across update cycles. Each cycle snapshots
        # these into a fresh YouTubeLiveCoordinatorData; self.data itself is
        # never mutated in place.
        self._streams: list[UpcomingStream] = []
        self._stream_states: dict[str, StreamStatus] = {}
        # video_id -> UpcomingStream
        self._stream_metadata: dict[str, UpcomingStream] = {}

    @staticmethod
    def handle_key(handle: str) -> str:
        """Canonical key for matching handles."""
        h = handle.strip()
        if not h.startswith("@"):
            h = f"@{h}"
        return h.lower()

    async def _async_update_data(self) -> YouTubeLiveCoordinatorData:
        """Update data from YouTube."""
        now = dt_util.utcnow()

        # Check if it's time for a broad calendar update
        if (
            self._last_calendar_update is None
            or now - self._last_calendar_update >= DEFAULT_CALENDAR_INTERVAL
        ):
            await self._update_calendar_data()
            self._last_calendar_update = now

        await self._update_stream_statuses()

        return YouTubeLiveCoordinatorData(
            streams=list(self._streams),
            statuses=dict(self._stream_states),
            stream_metadata=dict(self._stream_metadata),
        )

    async def _update_calendar_data(self) -> None:
        """Fetch upcoming streams for all channels."""
        self.channel_handles = list(
            self.config_entry.data.get(CONF_CHANNEL_HANDLES, [])
        )
        current_keys = {self.handle_key(h) for h in self.channel_handles}
        self.channel_thumbnail_urls = {k: v for k, v in self.channel_thumbnail_urls.items() if k in current_keys}
        self.channel_names = {k: v for k, v in self.channel_names.items() if k in current_keys}
        self.channel_ids = {k: v for k, v in self.channel_ids.items() if k in current_keys}

        try:
            streams: list[UpcomingStream] = await self.hass.async_add_executor_job(
                get_upcoming_streams, self.channel_handles
            )
        except Exception as err:
            _LOGGER.error("Error fetching streams: %s", err, exc_info=True)
            # Keep the previously fetched streams if we have any; only fail the
            # update outright when we have nothing to fall back on.
            if not self._streams:
                raise UpdateFailed(f"Error fetching streams: {err}") from err
            streams = self._streams

        # Update metadata maps
        for stream in streams:
            key = self.stream_handle_key(stream)
            if key:
                if stream.channel_thumbnail_url:
                    self.channel_thumbnail_urls[key] = stream.channel_thumbnail_url
                if stream.channel:
                    self.channel_names[key] = stream.channel
                if stream.channel_id:
                    self.channel_ids[key] = stream.channel_id

        # For channels without streams, fetch info directly
        for handle in self.channel_handles:
            key = self.handle_key(handle)
            if key not in self.channel_thumbnail_urls or key not in self.channel_names:
                try:
                    info = await self.hass.async_add_executor_job(get_channel_info, handle)
                    if info:
                        self.channel_names[key] = info.name
                        if info.channel_id:
                            self.channel_ids[key] = info.channel_id
                        if info.thumbnail_url:
                            self.channel_thumbnail_urls[key] = info.thumbnail_url
                except Exception as err:
                    _LOGGER.debug("Could not fetch channel info for %s: %s", handle, err)

        self._streams = streams

    def stream_handle_key(self, stream: UpcomingStream) -> str | None:
        """Find the handle key associated with a stream."""
        for handle in self.channel_handles:
            key = self.handle_key(handle)
            channel_id = self.channel_ids.get(key)
            if channel_id and stream.channel_id == channel_id:
                return key
            display_name = self.channel_names.get(key)
            bare = handle.lstrip("@").lower()
            name = (stream.channel or "").lower()
            if (display_name and name == display_name.lower()) or name == bare:
                return key
        return None

    def _is_in_active_window(self, stream: UpcomingStream) -> bool:
        """Check if a stream is in the active polling window."""
        now = dt_util.utcnow()
        window_start = stream.scheduled_start - timedelta(minutes=ACTIVE_WINDOW_MINUTES)
        window_end = stream.scheduled_start + timedelta(minutes=ACTIVE_WINDOW_MINUTES)

        state = self._stream_states.get(stream.video_id)
        if state and state.ended:
            return False
        if state and state.was_live:
            return True

        return window_start <= now <= window_end

    async def _update_stream_statuses(self) -> None:
        """Poll live status for active streams."""
        streams = self._streams
        now = dt_util.utcnow()

        # Cleanup states
        known_ids = {s.video_id for s in streams}
        self._stream_states = {
            vid: state
            for vid, state in self._stream_states.items()
            if vid in known_ids or state.is_live or (state.was_live and not state.ended)
        }
        self._stream_metadata = {
            vid: meta
            for vid, meta in self._stream_metadata.items()
            if vid in self._stream_states
        }

        # Identify streams to poll
        for stream in streams:
            if stream.video_id not in self._stream_states:
                if self._is_in_active_window(stream) or stream.live:
                    self._stream_states[stream.video_id] = StreamStatus()
            
            if stream.video_id in self._stream_states and stream.video_id not in self._stream_metadata:
                self._stream_metadata[stream.video_id] = stream

        # Poll them
        for video_id, state in list(self._stream_states.items()):
            if state.ended:
                continue
            
            stream = next((s for s in streams if s.video_id == video_id), None)
            
            # Decide whether to poll
            should_poll = state.is_live
            if not should_poll and stream:
                should_poll = stream.live or self._is_in_active_window(stream)
            
            if not should_poll:
                continue

            try:
                result: StreamLiveStatus = await self.hass.async_add_executor_job(is_stream_live, video_id)
                if stream and result.actual_start:
                    stream.scheduled_start = result.actual_start
                
                state.is_live = result.is_live
                if state.is_live:
                    state.was_live = True
                elif state.was_live:
                    state.ended = True
                    state.ended_at = now
                elif stream and now > stream.scheduled_start + timedelta(minutes=ACTIVE_WINDOW_MINUTES):
                    state.ended = True
            except Exception as err:
                _LOGGER.warning("Error checking live status for %s: %s", video_id, err)

    def relevant_streams(self) -> list[UpcomingStream]:
        """Return the shared set of streams to surface across all platforms.

        This is the single source of truth for "which streams exist": every
        upcoming/known stream, plus any stream that is still live but has
        dropped out of the scraper's list (recovered from stream_metadata).
        """
        if not self.data:
            return []
        streams = list(self.data.streams)
        known = {s.video_id for s in streams}
        for video_id, status in self.data.statuses.items():
            if status.is_live and video_id not in known:
                meta = self.data.stream_metadata.get(video_id)
                if meta is not None:
                    streams.append(meta)
        return streams

    def stream_end_time(self, stream: UpcomingStream) -> datetime:
        """Return the effective end time for a stream.

        Uses the observed end time once a stream that was live has ended,
        otherwise falls back to the default stream duration.
        """
        status = self.data.statuses.get(stream.video_id) if self.data else None
        if status and status.ended and status.ended_at:
            return status.ended_at
        return stream.scheduled_start + timedelta(hours=DEFAULT_STREAM_DURATION_HOURS)

    def is_stream_active(
        self, stream: UpcomingStream, now: datetime | None = None
    ) -> bool:
        """Return whether a stream is still live or has not yet finished."""
        status = self.data.statuses.get(stream.video_id) if self.data else None
        if status and status.is_live:
            return True
        if now is None:
            now = dt_util.now()
        return self.stream_end_time(stream) > now

    def streams_for_handle(self, handle: str) -> list[UpcomingStream]:
        """Return the streams that belong to a specific handle."""
        if not self.data or not self.data.streams:
            return []
        key = self.handle_key(handle)
        channel_id = self.channel_ids.get(key)
        display_name = self.channel_names.get(key)
        bare = handle.lstrip("@").lower()
        
        out: list[UpcomingStream] = []
        for stream in self.data.streams:
            if channel_id and stream.channel_id == channel_id:
                out.append(stream)
            else:
                name = (stream.channel or "").lower()
                if (display_name and name == display_name.lower()) or name == bare:
                    out.append(stream)
        return out
