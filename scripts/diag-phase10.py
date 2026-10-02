from pathlib import Path
import tempfile
from app.core import get_settings
from app.services.input import AttachmentStore

with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    safe = root / "safe"
    safe.mkdir()
    settings = get_settings()
    settings.INPUT_ENABLED = True
    settings.INPUT_SAFE_ROOTS = str(safe)
    settings.INPUT_ATTACHMENT_DIR = str(root / "attachments")
    settings.INPUT_ALLOWED_EXTENSIONS = ".txt"
    source = safe / "x.txt"
    source.write_text("hello", encoding="utf-8")
    store = AttachmentStore()
    print("initialized", flush=True)
    print(store.ingest_files([str(source)])[0], flush=True)
    print("listed", len(store.list_attachments()), flush=True)
