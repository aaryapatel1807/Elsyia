# Local Startup

Elsyia is configured to start its local services automatically after the current Windows user signs in. A shortcut named `Elsyia Local Services.lnk` is installed in the user Startup folder and launches `scripts/startup-elsyia.ps1` without opening a console window.

The script checks whether Ollama is already responding, starts `ollama serve` when necessary, waits for the Ollama API, and then starts the backend from `backend/.venv/Scripts/python.exe`. It waits for the backend health endpoint and writes diagnostic messages to `logs/startup.log`.

To test the sequence manually, run PowerShell with the following command from the project root:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\startup-elsyia.ps1
```

To disable automatic startup, remove `Elsyia Local Services.lnk` from `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup`. The project script remains available for manual use.

The configuration is user-level and does not require administrator privileges. Windows Task Scheduler registration was unavailable because the current session returned `Access is denied`, so the Startup-folder shortcut is the active fallback.
