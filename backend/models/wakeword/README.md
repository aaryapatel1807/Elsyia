# Wake-word models — packaging contract

The stock build needs nothing here: the default openWakeWord community
model (`hey_jarvis`) is downloaded automatically the first time the
wake-word listener is enabled.

To ship a custom trained model (e.g. `hey_elsyia.onnx` from the openWakeWord
training notebook), drop the `.onnx` file into this directory. It is
bundled into the installer by electron-builder `extraResources` and lands
at `<resources>/backend/wakeword/` in the installed app. Point the backend
at it with the `ELSYIA_WAKE_MODEL` environment variable (absolute path), or
through the in-app setting once supported.
