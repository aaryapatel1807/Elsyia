# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: freeze the Jev FastAPI backend into one executable.

Build (any platform — the binary always targets the machine it is built on):
    cd backend && /path/to/venv/bin/python -m PyInstaller --noconfirm --clean jev-backend.spec
or simply, from frontend/:
    npm run build:backend

Output: backend/dist/jev-backend  (jev-backend.exe on Windows)

Notes:
- Onefile mode: the binary unpacks to a temp dir on every launch. On
  machines with a tiny /tmp, set TMPDIR to a roomier directory.
- Set JEV_BACKEND_CONSOLE=1 to keep a console window on Windows
  (useful when debugging the first packaged build).
"""

import os
import sys

# PyInstaller executes the spec via exec() without __file__; it provides
# SPECPATH (the directory containing the spec file) instead.
HERE = os.path.abspath(SPECPATH)  # noqa: F821
REPO_ROOT = os.path.abspath(os.path.join(HERE, os.pardir))

# Make the local `app` package importable for collect_all() below.
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from PyInstaller.utils.hooks import collect_all  # noqa: E402

block_cipher = None


def _collect(pkg):
    """collect_all() that tolerates optional packages (e.g. openwakeword)."""
    try:
        return collect_all(pkg)
    except Exception as exc:  # package not installed yet — skip it
        print(f"[jev-backend.spec] optional package '{pkg}' not collected: {exc}")
        return [], [], []


datas: list[tuple[str, str]] = []
binaries: list[tuple[str, str]] = []
hiddenimports: list[str] = []

# The whole backend package (covers routers, tools and other modules that
# are imported dynamically at runtime).
d, b, h = collect_all("app")
datas += d
binaries += b
hiddenimports += h

# Heavy native dependencies: binaries + data files must be collected
# explicitly or the frozen app crashes on import.
for pkg in ("ctranslate2", "onnxruntime", "faster_whisper", "piper", "openwakeword"):
    d, b, h = _collect(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# Repo-root resources that the backend resolves at runtime through
# Path(__file__).parents[4] — inside the frozen app that is sys._MEIPASS,
# so bundling them at the bundle root keeps every existing lookup working
# with zero code changes.
for resource in ("prompts", "plugins"):
    src = os.path.join(REPO_ROOT, resource)
    if os.path.isdir(src):
        datas.append((src, resource))

hiddenimports += [
    "app.main",
    # uvicorn pieces imported dynamically by uvicorn itself
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.loops.uvloop",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.http.httptools_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.protocols.websockets.wsproto_impl",
    "uvicorn.lifespan.on",
    "httptools",
    "uvloop",
    "websockets",
    "wsproto",
    "watchfiles",
]

# Exclude the GUI toolkit: nothing in the backend needs it and it only
# adds weight to the bundle.
excludes = ["tkinter", "Tkinter"]

console_mode = os.environ.get("JEV_BACKEND_CONSOLE", "") == "1"

a = Analysis(
    [os.path.join(HERE, "jev_backend_entry.py")],
    pathex=[HERE],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="jev-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX breaks several of the ML native libs; keep them intact
    upx_exclude=[],
    runtime_tmpdir=None,
    console=console_mode,  # no console window in the shipped app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
