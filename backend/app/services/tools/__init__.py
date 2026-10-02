"""Tool catalog and permission-aware registry for Elysia."""

from app.services.tools.base import Tool, ToolError
from app.services.tools.desktop_tools import LaunchApplicationTool
from app.services.tools.desktop_automation import (
    CloseWindowTool,
    DeleteDesktopFileTool,
    FocusWindowTool,
    GetActiveWindowTool,
    KeyboardTypeTool,
    ListWindowsTool,
    MoveDesktopFileTool,
    MoveResizeWindowTool,
    MouseClickTool,
    NetworkStatusTool,
    PressKeyTool,
    ReadClipboardTool,
    ReadDesktopFileTool,
    RestoreDesktopFileTool,
    WriteClipboardTool,
    WriteDesktopFileTool,
)
from app.services.tools.code_tools import (
    AnalyzeCodeRepositoryTool,
    CodeRepositoryStatusTool,
    IndexCodeRepositoryTool,
    SearchCodeRepositoryTool,
)
from app.services.tools.browser_tools import (
    BrowserSessionInfoTool,
    CloseBrowserSessionTool,
    DownloadBrowserFileTool,
    NavigateBrowserTool,
    ScrapeBrowserPageTool,
    ScreenshotBrowserPageTool,
)
from app.services.tools.desktop_controls import (
    GetDisplayBrightnessTool,
    GetPowerPlanTool,
    GetSystemVolumeTool,
    OpenWindowsSettingsTool,
    SetDisplayBrightnessTool,
    SetPowerPlanTool,
    SetSystemMuteTool,
    SetSystemVolumeTool,
)
from app.services.tools.file_tools import SearchLocalFilesTool, SummarizeLocalDocumentTool
from app.services.tools.draft_tools import DraftTextTool
from app.services.tools.reminders import CancelReminderTool, CreateReminderTool, ListRemindersTool
from app.services.tools.registry import ToolExecutionResult, ToolRegistry, registry
from app.services.tools.system_tools import GetCurrentTimeTool, GetSystemInfoTool
from app.services.tools.vision_tools import CaptureScreenTool, OcrImageTool
from app.services.tools.web_tools import (
    FetchUrlTool,
    GetWorldFinanceNewsTool,
    GetWorldNewsTool,
    SearchWebTool,
)

AVAILABLE_TOOLS: list[Tool] = [
    GetCurrentTimeTool(),
    GetSystemInfoTool(),
    GetWorldNewsTool(),
    GetWorldFinanceNewsTool(),
    FetchUrlTool(),
    SearchWebTool(),
    LaunchApplicationTool(),
    SearchLocalFilesTool(),
    SummarizeLocalDocumentTool(),
    CreateReminderTool(),
    ListRemindersTool(),
    CancelReminderTool(),
    DraftTextTool(),
    ListWindowsTool(),
    GetActiveWindowTool(),
    FocusWindowTool(),
    MoveResizeWindowTool(),
    CloseWindowTool(),
    ReadDesktopFileTool(),
    WriteDesktopFileTool(),
    MoveDesktopFileTool(),
    DeleteDesktopFileTool(),
    RestoreDesktopFileTool(),
    ReadClipboardTool(),
    WriteClipboardTool(),
    NetworkStatusTool(),
    PressKeyTool(),
    KeyboardTypeTool(),
    MouseClickTool(),
    GetSystemVolumeTool(),
    SetSystemVolumeTool(),
    SetSystemMuteTool(),
    GetDisplayBrightnessTool(),
    GetPowerPlanTool(),
    SetDisplayBrightnessTool(),
    SetPowerPlanTool(),
    OpenWindowsSettingsTool(),
    NavigateBrowserTool(),
    BrowserSessionInfoTool(),
    ScrapeBrowserPageTool(),
    CloseBrowserSessionTool(),
    ScreenshotBrowserPageTool(),
    DownloadBrowserFileTool(),
    IndexCodeRepositoryTool(),
    AnalyzeCodeRepositoryTool(),
    SearchCodeRepositoryTool(),
    CodeRepositoryStatusTool(),
    CaptureScreenTool(),
    OcrImageTool(),
]

for _tool in AVAILABLE_TOOLS:
    if registry.get(_tool.name) is None:
        registry.register(
            _tool,
            confirmation_required=_tool.name in {
                "launch_application",
                "create_reminder",
                "cancel_reminder",
                "move_resize_window",
                "close_window",
                "write_desktop_file",
                "move_desktop_file",
                "delete_desktop_file",
                "write_clipboard",
                "press_key",
                "keyboard_type",
                "mouse_click",
                "set_system_volume",
                "set_system_mute",
                "set_display_brightness",
                "set_power_plan",
                "open_windows_settings",
                "screenshot_browser_page",
                "download_browser_file",
                "capture_screen",
                "ocr_image",
            },
        )

TOOLS_BY_NAME: dict[str, Tool] = {tool.name: tool for tool in AVAILABLE_TOOLS}

__all__ = [
    "Tool",
    "ToolError",
    "ToolExecutionResult",
    "ToolRegistry",
    "AVAILABLE_TOOLS",
    "TOOLS_BY_NAME",
    "registry",
]
