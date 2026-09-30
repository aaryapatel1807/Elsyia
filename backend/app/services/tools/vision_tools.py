from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core import get_settings
from app.services.tools.base import Tool, ToolError


def _root() -> Path:
    return Path(__file__).resolve().parents[4]


def _dir() -> Path:
    value = Path(get_settings().INPUT_ATTACHMENT_DIR)
    if not value.is_absolute():
        value = _root() / value
    value.mkdir(parents=True, exist_ok=True)
    return value.resolve()


def _safe_image(value: str) -> Path:
    if not value or len(value) > 1024:
        raise ToolError("Image path is invalid")
    try:
        path = Path(value).resolve(strict=True)
    except OSError as exc:
        raise ToolError("Image path cannot be resolved") from exc
    roots = [_dir()]
    for raw in get_settings().INPUT_SAFE_ROOTS.split(";"):
        if raw.strip():
            roots.append(Path(raw.strip()).expanduser().resolve())
    if path.is_symlink() or not any(path == root or root in path.parents for root in roots):
        raise ToolError("Image path is outside configured local roots")
    if path.suffix.lower() not in {".bmp", ".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        raise ToolError("OCR supports only local image files")
    return path


class CaptureScreenTool(Tool):
    name = "capture_screen"
    description = "Capture the primary Windows display to a private local image after confirmation."

    async def run(self, **kwargs: Any) -> dict[str, Any]:
        if sys.platform != "win32" or not get_settings().VISION_ENABLED:
            raise ToolError("Screen capture is disabled or supported only on Windows")
        path = _dir() / f"screenshot-{uuid4().hex}.png"
        script = "$ErrorActionPreference='Stop'; Add-Type -AssemblyName System.Drawing; Add-Type -AssemblyName System.Windows.Forms; $b=[System.Windows.Forms.Screen]::PrimaryScreen.Bounds; $i=New-Object Drawing.Bitmap($b.Width,$b.Height); $g=[Drawing.Graphics]::FromImage($i); $g.CopyFromScreen($b.Location,[Drawing.Point]::Empty,$b.Size); $i.Save('{0}',[Drawing.Imaging.ImageFormat]::Png); $g.Dispose(); $i.Dispose()".format(str(path).replace("'", "''"))
        try:
            result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], check=False, capture_output=True, text=True, timeout=20, shell=False)
        except subprocess.TimeoutExpired as exc:
            raise ToolError("Screen capture timed out") from exc
        if result.returncode != 0 or not path.exists():
            raise ToolError("Windows refused the screen capture request")
        return {"status": "captured", "image_path": str(path), "local_only": True}


class OcrImageTool(Tool):
    name = "ocr_image"
    description = "Run bounded local OCR on a trusted local image after confirmation; no cloud service is used."

    async def run(self, image_path: str, **kwargs: Any) -> dict[str, Any]:
        if not get_settings().VISION_ENABLED:
            raise ToolError("Vision tools are disabled by configuration")
        path = _safe_image(image_path)
        executable = shutil.which("tesseract")
        if executable is None:
            raise ToolError("Local OCR engine is unavailable; install Tesseract locally and retry")
        try:
            result = subprocess.run([executable, str(path), "stdout", "--psm", "6"], check=False, capture_output=True, text=True, timeout=get_settings().VISION_OCR_TIMEOUT_SECONDS, shell=False)
        except subprocess.TimeoutExpired as exc:
            raise ToolError("Local OCR timed out") from exc
        if result.returncode != 0:
            raise ToolError("Local OCR failed")
        text = result.stdout[: get_settings().VISION_MAX_OCR_CHARS]
        return {"status": "completed", "ocr_text": text, "truncated": len(result.stdout) > len(text), "local_only": True}
