# YouTube Live for Home Assistant

A Home Assistant custom integration that monitors YouTube channels for upcoming live streams. It creates a shared calendar with scheduled streams and a binary sensor per channel indicating whether the channel is currently live.

## Features

- **Shared calendar** showing upcoming live streams from all monitored YouTube channels
- **Per-channel binary sensor** that turns on when the channel goes live
- Automatic polling: calendar updates hourly, live status checks every minute within a 15-minute window around the scheduled start time
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

Click the button to add a YouTube Live channel to Home Assistant.

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=youtube_live)

Enter the handle of the Youtube channel and click _Submit_.

![Add channel](https://raw.githubusercontent.com/jonnybergdahl/HomeAssistant_YT_Live_Integration/main/images/add.png)

Optionally select an area and click _Skip and finish_.

![Add area](https://raw.githubusercontent.com/jonnybergdahl/HomeAssistant_YT_Live_Integration/main/images/area.png)

You can also set it up manually:

1. Go to **Settings** > **Devices & services** > **Add integration**
2. Search for **YouTube Live**
3. Enter the channel handle of the YouTube channel you want to monitor (e.g. `@home_assistant`)
4. Click **Submit**

To monitor multiple channels, repeat the setup for each channel.

## Entities

### Calendar

A single **YouTube Live Streams** calendar entity is created that aggregates upcoming live streams from all monitored channels. The calendar is updated once per hour.

![Calendar](https://raw.githubusercontent.com/jonnybergdahl/HomeAssistant_YT_Live_Integration/main/images/calendar.png)

### Binary sensor

Each channel gets a binary sensor (e.g. `binary_sensor.home_assistant_live`). The sensor turns **on** when any stream on the channel is live and **off** otherwise.

The friendly name dynamically shows the title of the next upcoming or current stream. When no streams are scheduled it falls back to **\<channel\> Live**. The entity picture shows the stream thumbnail.

Live status polling starts 15 minutes before the scheduled start time and runs every minute. Polling stops when the stream ends, or 15 minutes after the scheduled start time if the stream never started.

Each binary sensor includes extra state attributes:

| Attribute | Description |
|---|---|
| `channel_handle` | Channel handle (e.g. `@home_assistant`) |
| `channel_name` | Channel display name (e.g. `Home Assistant`) |
| `url` | URL of the next upcoming or current stream |
| `stream_start` | Scheduled start time (ISO 8601) |

# Usage

To get a single sensor that tells if any Youtube channel is live, create a binary Template sensor

Show as: Running<br/>
State:
```yaml
{{ integration_entities('youtube_live') 
   | select('is_state', 'on') 
   | list | count > 0 }}```