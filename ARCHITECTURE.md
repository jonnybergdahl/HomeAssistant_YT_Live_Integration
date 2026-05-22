# Architecture of YouTube Live Integration

This document describes the architectural design and data flow of the YouTube Live integration for Home Assistant.

## Overview

The YouTube Live integration allows users to track upcoming and live streams from specified YouTube channels. It groups channels into "Channel Groups," each appearing as a single device in Home Assistant with associated sensors and a calendar.

The integration uses the `yt-live-scraper` library to fetch data from YouTube without requiring an official API key, relying on public channel pages.

## Component Diagram

```mermaid
graph TD
    HA[Home Assistant] --> Integration[YouTube Live Integration]
    Integration --> ConfigFlow[Config Flow]
    Integration --> Coordinator[YouTubeLiveCoordinator]
    
    Coordinator --> Scraper[yt-live-scraper]
    
    Scraper --> YouTube[YouTube Public Pages]
    
    Integration --> Platforms[Platforms]
    
    subgraph Platforms
        Calendar[Calendar]
        Sensor[Upcoming Sensor]
        BinarySensor[Live Status Sensors]
    end
    
    Coordinator -.-> Calendar
    Coordinator -.-> Sensor
    Coordinator -.-> BinarySensor
```

## Core Components

### 1. Configuration Flow (`config_flow.py`)
Handles the setup of the integration. Users define a **Channel Group** by giving it a name and a list of YouTube channel handles (e.g., `@jonnybergdahl`).
- Validates handles during setup using `yt-live-scraper`.
- Supports Options Flow for adding or removing channels from an existing group.

### 2. Coordinator (`coordinator.py`)
The integration uses a single `YouTubeLiveCoordinator` to manage data fetching and sharing across entities.

#### YouTubeLiveCoordinator
- **Responsibility**: Manages both broad channel scans for upcoming streams and targeted live-status checks for active streams.
- **Data Source**: `yt-live-scraper.scraper.get_upcoming_streams` and `yt-live-scraper.scraper.is_stream_live`.
- **Update Strategy**:
    - **Broad Update**: Every 10 minutes (`DEFAULT_CALENDAR_INTERVAL`), it fetches the full list of upcoming streams for all channels in the group.
    - **Targeted Update**: Every 1 minute (`DEFAULT_SENSOR_INTERVAL`), it checks the live status of streams that are either currently live or scheduled to start soon.
- **Data**: A `YouTubeLiveCoordinatorData` object containing:
    - `streams`: Current list of upcoming streams.
    - `statuses`: Map of video IDs to their live/polling state.
    - `stream_metadata`: Map of video IDs to stream details, preserved even if a stream drops from the main scraper list while live.

### 3. Platforms

#### Calendar (`calendar.py`)
Displays upcoming streams as events. 
- Uses unified data to show both upcoming and currently live streams.
- Events include the channel name, stream title, and a link to the video.

#### Sensor (`sensor.py`)
Provides a `YouTubeLiveUpcomingSensor` designed for consumption by external devices like ESPHome.
- **State**: Count of upcoming streams.
- **Attributes**: A flat list of the next 5 upcoming streams (titles, start times, video IDs, and channel names).

#### Binary Sensor (`binary_sensor.py`)
Provides real-time "Live" status indicators.
- **Channel Sensor**: One per channel in the group. `on` when that specific channel is live.
- **Group Sensor**: One per group. `on` if *any* channel in the group is live.
- Attributes include the current or next stream's title, thumbnail URL, and video ID.

## Data Flow

1. **Broad Discovery**: Periodically polls YouTube for upcoming streams for all configured handles.
2. **Active Monitoring**: Identifies streams in the "active window" and polls their specific status pages frequently.
3. **Unified Observation**: 
    - The **Calendar** updates its view based on all known streams.
    - The **Upcoming Sensor** updates its count and attributes.
    - **Binary Sensors** flip to `on` as soon as a `live` state is detected for a video.

## Design Decisions

- **No API Key**: By using `yt-live-scraper`, the integration avoids the complexity and quota limits of the official YouTube Data API v3.
- **Polling Strategy**: Two-tier polling (Calendar vs. Status) balances the need for timely live-status updates with the overhead of scanning entire channel pages.
- **Channel Groups**: Grouping channels allows for organized dashboards (e.g., "Tech YouTubers" group vs. "Gaming" group).
