# Phase 3 Vision Progress

**Milestone:** Local screen capture and OCR foundation  
**Status:** Foundation implemented

## Implemented

Elsyia now exposes `capture_screen` and `ocr_image` through the existing permission-aware tool registry. Screen capture is Windows-only, writes a generated PNG into the private local attachment directory, and requires the existing confirmation boundary before execution. The capture path never invokes a shell command from user input and is bounded by the configured vision enablement and pixel policy.

OCR accepts only existing local image paths inside the Phase 10 attachment directory or explicitly configured input safe roots. Symlinks, traversal, unsupported extensions, unresolvable paths, and oversized OCR output are rejected. OCR uses a locally installed Tesseract executable when available and fails closed with an actionable local-install message when it is not available. No image or OCR text is sent to a cloud provider by this tool.

Audit redaction now treats image paths, screenshot paths, OCR text, regions, and vision prompts as sensitive values. The tool API continues to record only redacted local audit metadata.

## Configuration

```env
VISION_ENABLED=true
VISION_MAX_PIXELS=16000000
VISION_OCR_TIMEOUT_SECONDS=20
VISION_MAX_OCR_CHARS=12000
```

## Verification

The backend compiled successfully, and the Phase 3 vision regression suite passed four tests covering registration, confirmation gating, local path restrictions, disabled-vision behavior, and safe OCR failure when a local engine is unavailable.

## Remaining vision work

This milestone does not claim full multimodal vision. Region capture, window-specific capture, camera input, local image understanding, handwriting recognition, screenshot annotation, and a bundled OCR runtime remain future work. The current implementation deliberately avoids automatically uploading images or sending them to an LLM.
