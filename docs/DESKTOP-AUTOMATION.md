# Elysia Phase 5 Desktop Automation

Phase 5 adds controlled Windows desktop automation on top of the Phase 4 registry. Every action is local, bounded, and exposed through the same structured result and audit pipeline.

## Safety model

Read-only inspection is available without confirmation. Actions that change files, clipboard content, keyboard or mouse state, window geometry, or process state require confirmation. Input automation is additionally disabled unless `DESKTOP_INPUT_ENABLED=true` is explicitly configured.

Filesystem operations are limited to `DESKTOP_SAFE_ROOTS`. A blank value uses the current user’s Desktop, Documents, Downloads, and the project’s local data directory. Path resolution rejects traversal outside those roots and does not follow symlinks. Deletion is implemented as a reversible move into `data/elysia_trash/`, not an immediate permanent delete.

The action registry applies a timeout and rate limit. Sensitive arguments such as file paths, clipboard text, keyboard text, and window titles are redacted by the existing audit logger.

## Phase 5 tool groups

| Group | Tools | Confirmation |
|---|---|---|
| Window inspection | `list_windows`, `get_active_window` | No |
| Window control | `focus_window`, `move_resize_window`, `close_window` | Focus no; others yes |
| Volume control | `get_system_volume`, `set_system_volume`, `set_system_mute` | Read no; changes yes |
| Brightness control | `get_display_brightness`, `set_display_brightness` | Read no; changes yes |
| Settings pages | `open_windows_settings` | Required |
| File inspection | `read_desktop_file`, `network_status` | No |
| File changes | `write_desktop_file`, `move_desktop_file`, `delete_desktop_file`, `restore_desktop_file` | Changes yes; restore no |
| Clipboard | `read_clipboard`, `write_clipboard` | Read no; write yes |
| Input | `keyboard_type`, `press_key`, `mouse_click` | Yes and opt-in |
| Existing launcher | `launch_application` | Yes |

## Recovery

`delete_desktop_file` moves a file or empty directory into the local trash directory and returns a restore token. `restore_desktop_file` uses that token to restore the item to its original path when the destination is available. File moves return their original and destination paths so the operation can be reversed manually.

## Configuration

```env
DESKTOP_SAFE_ROOTS=
DESKTOP_MAX_FILE_BYTES=1000000
DESKTOP_CLIPBOARD_MAX_CHARS=10000
DESKTOP_INPUT_ENABLED=false
DESKTOP_ACTION_TIMEOUT_SECONDS=5
DESKTOP_ACTIONS_PER_MINUTE=30
DESKTOP_TRASH_PATH=data/elysia_trash
```

Windows audio control uses the local Core Audio binding and brightness control uses the Windows WMI monitor interfaces. Some external monitors and virtual audio devices may not support these controls; unsupported hardware returns a safe structured error without changing anything.

## Planned API

The tools use the existing direct registry endpoint and Phase 4 plugin-aware catalog. A dedicated convenience API can be added after the tool contracts stabilize:

```http
GET /api/v1/tools/list_windows
POST /api/v1/tools/focus_window
POST /api/v1/tools/write_desktop_file
POST /api/v1/tools/keyboard_type
```

No arbitrary shell execution, arbitrary executable paths, hidden keystrokes, permanent deletion, or unrestricted filesystem access is permitted.
