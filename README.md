# YouTube Live for Home Assistant

A Home Assistant custom integration that monitors YouTube channels for upcoming live streams. Channels are organised into **groups** (e.g. "Gaming", "Technology"): each group becomes a device in Home Assistant with a calendar of its upcoming streams, a binary sensor for every channel in the group, and an aggregate "any channel live" binary sensor.

## Features

- **Channel groups** — organise the channels you monitor into named groups (one config entry per group)
- **Per-group calendar** listing upcoming live streams for that group's channels
- **Per-channel binary sensor** that turns on when that specific channel goes live
- **Aggregate group sensor** that turns on when *any* channel in the group is live
- Edit the channels in a group at any time via the integration's options
- Automatic polling: calendars update hourly; live status checks run every minute within a 15-minute window around the scheduled start time
- No API key required

## Installation

### HACS (recommended)

Click the button to add this repository to HACS.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=jonnybergdahl&category=Integration&repository=HomeAssistant_YT_Live_Integration)

Then restart Home Assistant.

You can also do the above manually:
1. Open HACS in your Home Assistant instance
2. Click the three-dot menu in the top right corner and select **Custom repositories**
3. Add `https://github.com/jonnybergdahl/HomeAssistant_YT_Live_Integration` as a custom repository with category **Integration**
4. Click **Add**
5. Search for **YouTube Live** in HACS and click **Download**
6. Restart Home Assistant

### Manual

1. Copy the `custom_components/youtube_live` folder into your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant

## Setup

Click the button to add a YouTube Live channel group to Home Assistant.

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=youtube_live)

1. Pick a **group name** (e.g. `Gaming`, `Technology`). This will be the device name in Home Assistant.
2. Add one or more **channel handles** (e.g. `@home_assistant`) using the list control — click **Add** to enter each handle.
3. Click **Submit**.

You can also set it up manually:

1. Go to **Settings** > **Devices & services** > **Add integration**
2. Search for **YouTube Live**
3. Enter a group name and the channel handles you want to include
4. Click **Submit**

To add or remove channels later, open the integration's **Configure** action and edit the list. Changes take effect immediately.

Create additional groups the same way — each group is independent and gets its own device, calendar, and sensors.

## Entities

Every group produces one Home Assistant device containing:

### Calendar

One **`calendar.youtube_live_<group>`** entity listing upcoming live streams for that group's channels. Updated once per hour.

### Per-channel binary sensors

One **`binary_sensor.youtube_live_<handle>`** per channel in the group. The sensor turns **on** when any stream on that channel is currently live, **off** otherwise.

The friendly name dynamically shows the title of the channel's next upcoming or current stream. When no streams are scheduled it falls back to **\<channel\> Live**. The entity picture shows the stream thumbnail when a stream is live or upcoming, and the channel's avatar otherwise.

Live status polling starts 15 minutes before the scheduled start time and runs every minute. Polling stops when the stream ends, or 15 minutes after the scheduled start time if the stream never started.

Each per-channel sensor includes extra state attributes:

| Attribute | Description |
|---|---|
| `channel_handle` | Channel handle (e.g. `@home_assistant`) |
| `channel_name` | Channel display name (e.g. `Home Assistant`) |
| `group` | Name of the group this channel belongs to |
| `stream_id` | Video ID of the next upcoming or current stream |
| `url` | URL of the next upcoming or current stream |
| `stream_start` | Scheduled start time (ISO 8601) |

### Group aggregate sensor

One **`binary_sensor.youtube_live_<group>_any_live`** per group. Turns **on** whenever any channel in the group is currently live. Handy for automations like "notify me when anything in my Gaming group starts streaming".

Attributes:

| Attribute | Description |
|---|---|
| `group` | Group name |
| `channel_handles` | List of channel handles in the group |
| `live_stream_ids` | Video IDs of streams currently live |
| `live_count` | Number of streams currently live |

### Upcoming streams sensor (for ESPHome)

One **`sensor.youtube_live_<group>_upcoming`** per group. The state is an integer count of upcoming streams (max 5). 

This sensor is designed for easy consumption by ESPHome devices (e.g., using `text_sensor` with `attribute` mapping). It provides a flat list of the next 5 upcoming streams as attributes.

Attributes:

| Attribute | Description |
|---|---|
| `event_i_title` | Stream title (truncated to 80 chars) |
| `event_i_start` | Scheduled start time (ISO 8601 UTC) |
| `event_i_video_id` | YouTube video ID |
| `event_i_channel` | Channel name |
| `event_i_duration` | Expected duration in minutes |

...where `i` is 0 to 4. Empty slots are represented as empty strings `""`.

## Usage

To get a single sensor that tells if *any* channel across *all* groups is live, create a binary Template sensor:

Show as: Running<br/>
State:
```yaml
{{ integration_entities('youtube_live')
   | select('search', '_any_live$')
   | select('is_state', 'on')
   | list | count > 0 }}
```
