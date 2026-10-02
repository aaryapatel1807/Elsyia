# Real-Time Data Source Configuration

Elsyia now supports an explicit, fail-closed real-time update path based on a fixed allowlist of RSS feeds from BBC World, CNBC, The New York Times, Al Jazeera, Bloomberg, Reuters, and MarketWatch. Feed requests use bounded timeouts, reject redirects, parse only RSS item metadata, and return at most the configured number of headlines. No API key is required for these feeds.

The local environment is configured with:

```env
REALTIME_DATA_ENABLED=true
REALTIME_DATA_TIMEOUT_SECONDS=8
REALTIME_DATA_MAX_ITEMS=12
```

Daily-update phrases such as “What is the update today?” are routed directly to the feed tool instead of the local language model. The spoken response includes the first three retrieved titles, while structured tool metadata retains the bounded result list. If the feature is disabled or all feeds fail, Elsyia returns an explicit failure rather than inventing a current update. The language model is not used to summarize absent current data.

The source selection is based on the official feed endpoints already maintained in the project and the Open-Meteo API was reviewed as a reliable keyless option for future weather-specific integration. Weather, traffic, prices, scores, and other live-data questions remain fail-closed unless a corresponding verified tool is added; the RSS configuration does not pretend to answer those categories.

## Verification

The running backend was restarted after configuration. A real request for “What is the update today?” returned `model=local-tool-router`, 12 structured headlines, and three actual feed titles in the spoken response. The response no longer contains the previous generic, unsupported claim about system improvements.
