# Phase 6 Browser Artifact Progress

**Milestone:** Guarded visible screenshots and same-origin downloads  
**Status:** Implemented; interactive form filling and high-impact actions remain disabled

Elsyia now supports two artifact operations on active isolated browser sessions. A visible viewport screenshot can be saved as a PNG under the configured local screenshot root. The screenshot is not full-page, is disabled by default, and is bounded by a configured byte limit. A browser download can be requested only for the active session origin, is revalidated against the trusted-domain policy, is saved under a controlled local download root, uses a sanitized bounded filename, and is rejected when its temporary stream exceeds the configured byte limit.

Both operations are registered as confirmation-required tools. The HTTP routes carry an explicit `confirmed` field, while the backend registry remains authoritative. Existing sessions still use non-persistent contexts with service workers blocked, HTTPS and exact-domain policy, redirect validation, action timeouts, session limits, and local redacted audit events. No login persistence, password autofill, CAPTCHA bypass, purchases, or arbitrary cross-origin download behavior was added.

## Configuration

```env
BROWSER_DOWNLOADS_ENABLED=false
BROWSER_DOWNLOAD_ROOT=data/browser_downloads
BROWSER_MAX_DOWNLOAD_BYTES=10000000
BROWSER_SCREENSHOTS_ENABLED=false
BROWSER_SCREENSHOT_ROOT=data/browser_screenshots
BROWSER_MAX_SCREENSHOT_BYTES=10000000
```

## Verification

The backend compiled successfully. The dedicated browser artifact suite passed three deterministic tests covering confirmation gating, disabled defaults, bounded visible screenshots, safe output filenames, and same-origin enforcement. No external website was automated and no real file was downloaded during validation.
