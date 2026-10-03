"""
Configuration Management

Loads settings from environment variables and provides type-safe access.
"""

import os
from functools import lru_cache
from pathlib import Path

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings.
    
    Loads from environment variables with validation.
    """
    
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parents[3] / ".env"),

        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    
    # === Server Settings ===
    HOST: str = Field(default="127.0.0.1", description="Server host")
    PORT: int = Field(default=8000, description="Server port")
    DEBUG: bool = Field(default=False, description="Debug mode")
    
    # === LLM Providers ===
    DEFAULT_LLM_PROVIDER: Literal["ollama", "openrouter", "gemini"] = Field(
        default="ollama",
        description="Default LLM provider"
    )
    DEFAULT_LLM_MODEL: str = Field(
        default="llama3.2",
        description="Default LLM model"
    )
    
    # Ollama
    OLLAMA_BASE_URL: str = Field(
        default="http://localhost:11434",
        description="Ollama API base URL"
    )
    OLLAMA_KEEP_ALIVE: str = Field(
        default="30m",
        description="Keep the local model loaded between requests"
    )
    OLLAMA_NUM_CTX: int = Field(
        default=2048,
        ge=512,
        le=32768,
        description="Small context window for lower prompt-evaluation latency"
    )
    OLLAMA_NUM_PREDICT: int = Field(
        default=128,
        ge=16,
        le=2048,
        description="Maximum generated tokens for concise fast answers"
    )
    OLLAMA_PREWARM: bool = Field(
        default=True,
        description="Warm the configured local model in the background at startup"
    )
    MAX_CONTEXT_MESSAGES: int = Field(
        default=12,
        ge=2,
        le=100,
        description="Maximum recent conversation messages sent to the model"
    )

    # OpenRouter
    OPENROUTER_API_KEY: str = Field(default="", description="OpenRouter API key")
    OPENROUTER_BASE_URL: str = Field(
        default="https://openrouter.ai/api/v1",
        description="OpenRouter API URL"
    )
    OPENROUTER_MODEL: str = Field(
        default="openai/gpt-4o-mini",
        description="Default OpenRouter model"
    )
    
    # Google Gemini
    GOOGLE_API_KEY: str = Field(default="", description="Google Gemini API key")
    GEMINI_MODEL: str = Field(
        default="gemini-2.0-flash",
        description="Default Gemini model"
    )
    GEMINI_BASE_URL: str = Field(
        default="https://generativelanguage.googleapis.com/v1beta",
        description="Google Generative Language API base URL"
    )

    # OpenAI (if using directly)
    OPENAI_API_KEY: str = Field(default="", description="OpenAI API key")

    # === Explicit Real-Time Data ===
    REALTIME_DATA_ENABLED: bool = Field(
        default=False,
        description="Allow bounded requests to the configured public real-time feeds",
    )
    REALTIME_DATA_TIMEOUT_SECONDS: int = Field(
        default=8,
        ge=2,
        le=30,
        description="Timeout for each real-time feed request",
    )
    REALTIME_DATA_MAX_ITEMS: int = Field(
        default=12,
        ge=1,
        le=50,
        description="Maximum current-data items returned to the assistant",
    )

    # === Speech Services ===
    DEFAULT_STT_PROVIDER: Literal["whisper"] = Field(
        default="whisper",
        description="Default STT provider"
    )
    DEFAULT_TTS_PROVIDER: Literal["piper"] = Field(
        default="piper",
        description="Default TTS provider"
    )
    
    # Whisper settings
    WHISPER_MODEL: Literal["tiny", "base", "small", "medium", "large"] = Field(
        default="tiny",
        description="Whisper model size"
    )
    WHISPER_DEVICE: Literal["cpu", "cuda"] = Field(
        default="cpu",
        description="Whisper device"
    )
    WHISPER_COMPUTE_TYPE: str = Field(
        default="int8",
        description="Whisper compute type"
    )
    WHISPER_BEAM_SIZE: int = Field(
        default=1,
        ge=1,
        le=5,
        description="Small beam size for faster local transcription"
    )
    VOICE_PREWARM: bool = Field(
        default=True,
        description="Warm STT and TTS models in the background at startup"
    )

    # Piper settings
    PIPER_VOICE: str = Field(
        default="en_US-lessac-medium",
        description="Piper voice model"
    )
    PIPER_MODELS_DIR: str = Field(
        default="models/piper",
        description="Directory containing downloaded Piper .onnx voice models"
    )
    PIPER_SPEED: float = Field(
        default=1.0,
        ge=0.5,
        le=2.0,
        description="Speech speed multiplier"
    )
    PIPER_MAX_CHARS: int = Field(
        default=320,
        ge=80,
        le=2000,
        description="Maximum characters synthesized in one spoken response"
    )
    
    # === Phase 3 Tools ===
    TOOLS_FILE_ROOTS: str = Field(
        default="",
        description="Comma-separated local roots allowed for file search and summarization; blank uses Desktop, Documents, and Downloads",
    )
    TOOLS_MAX_RESULTS: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Maximum filesystem matches returned by a read-only file tool",
    )
    TOOLS_MAX_FILE_BYTES: int = Field(
        default=1_000_000,
        ge=4096,
        le=10_000_000,
        description="Maximum text file size inspected by a document tool",
    )
    TOOLS_MAX_SUMMARY_CHARS: int = Field(
        default=12_000,
        ge=1000,
        le=50_000,
        description="Maximum extracted document characters sent to the local summarizer",
    )
    TOOLS_MAX_DRAFT_CHARS: int = Field(
        default=2_000,
        ge=100,
        le=10_000,
        description="Maximum characters returned by the draft-text tool",
    )
    TOOLS_EXCLUDED_DIRS: str = Field(
        default=".git,node_modules,.venv,venv,__pycache__",
        description="Comma-separated directory names skipped during local file search",
    )
    REMINDER_DB_PATH: str = Field(
        default="data/elysia_reminders.db",
        description="Local SQLite database for user reminders",
    )
    REMINDER_POLL_SECONDS: int = Field(
        default=15,
        ge=5,
        le=300,
        description="Interval used by the local reminder delivery worker",
    )
    REMINDER_WORKER_ENABLED: bool = Field(
        default=True,
        description="Run the local reminder delivery worker with the backend",
    )

    # === Phase 5 Desktop Automation ===
    DESKTOP_SAFE_ROOTS: str = Field(
        default="",
        description="Comma-separated local roots allowed for desktop file operations",
    )
    DESKTOP_MAX_FILE_BYTES: int = Field(
        default=1_000_000,
        ge=4096,
        le=10_000_000,
        description="Maximum file size read or written by desktop tools",
    )
    DESKTOP_CLIPBOARD_MAX_CHARS: int = Field(
        default=10_000,
        ge=100,
        le=100_000,
        description="Maximum clipboard text returned or written",
    )
    DESKTOP_INPUT_ENABLED: bool = Field(
        default=False,
        description="Explicit opt-in for keyboard and mouse simulation",
    )
    DESKTOP_SYSTEM_SETTINGS_ENABLED: bool = Field(
        default=False,
        description="Explicit opt-in to allowlisted direct Windows system-setting changes",
    )
    DESKTOP_ACTION_TIMEOUT_SECONDS: int = Field(
        default=5,
        ge=1,
        le=30,
        description="Timeout for bounded desktop subprocess actions",
    )
    DESKTOP_ACTIONS_PER_MINUTE: int = Field(
        default=30,
        ge=1,
        le=120,
        description="Maximum desktop actions allowed per rolling minute",
    )
    DESKTOP_TRASH_PATH: str = Field(
        default="data/elysia_trash",
        description="Local reversible trash directory for desktop deletion",
    )

    # === Phase 6 Browser Foundation ===
    BROWSER_ENABLED: bool = Field(
        default=True,
        description="Enable the local browser foundation",
    )
    BROWSER_HEADLESS: bool = Field(
        default=True,
        description="Run browser contexts headlessly by default",
    )
    BROWSER_ALLOWED_DOMAINS: str = Field(
        default="",
        description="Comma-separated exact domains allowed for browser navigation; blank disables navigation",
    )
    BROWSER_ALLOWED_SCHEMES: str = Field(
        default="https",
        description="Comma-separated URL schemes allowed for browser navigation",
    )
    BROWSER_MAX_SESSIONS: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum concurrent browser sessions",
    )
    BROWSER_SESSION_IDLE_SECONDS: int = Field(
        default=300,
        ge=30,
        le=3600,
        description="Idle browser session expiry in seconds",
    )
    BROWSER_SESSION_MAX_SECONDS: int = Field(
        default=1800,
        ge=60,
        le=7200,
        description="Maximum browser session lifetime in seconds",
    )
    BROWSER_NAVIGATION_TIMEOUT_SECONDS: int = Field(
        default=15,
        ge=3,
        le=120,
        description="Navigation timeout in seconds",
    )
    BROWSER_ACTION_TIMEOUT_SECONDS: int = Field(
        default=10,
        ge=2,
        le=120,
        description="Browser extraction/action timeout in seconds",
    )
    BROWSER_MAX_TEXT_CHARS: int = Field(
        default=20_000,
        ge=1000,
        le=100_000,
        description="Maximum visible page text returned by extraction",
    )
    BROWSER_MAX_LINKS: int = Field(
        default=100,
        ge=10,
        le=1000,
        description="Maximum links returned by extraction",
    )
    BROWSER_MAX_HEADINGS: int = Field(
        default=50,
        ge=5,
        le=500,
        description="Maximum headings returned by extraction",
    )
    BROWSER_MAX_TABLE_ROWS: int = Field(
        default=100,
        ge=10,
        le=1000,
        description="Maximum table rows returned by extraction",
    )
    BROWSER_DOWNLOADS_ENABLED: bool = Field(
        default=False,
        description="Enable guarded browser downloads",
    )
    BROWSER_DOWNLOAD_ROOT: str = Field(
        default="data/browser_downloads",
        description="Safe browser download directory",
    )
    BROWSER_MAX_DOWNLOAD_BYTES: int = Field(
        default=10_000_000,
        ge=100_000,
        le=100_000_000,
        description="Maximum browser download size",
    )
    BROWSER_SCREENSHOTS_ENABLED: bool = Field(
        default=False,
        description="Enable guarded browser screenshots",
    )
    BROWSER_SCREENSHOT_ROOT: str = Field(
        default="data/browser_screenshots",
        description="Safe browser screenshot directory",
    )
    BROWSER_MAX_SCREENSHOT_BYTES: int = Field(
        default=10_000_000,
        ge=100_000,
        le=100_000_000,
        description="Maximum visible browser screenshot size",
    )

    # === Phase 7 Code Assistant Foundation ===
    CODE_ENABLED: bool = Field(
        default=True,
        description="Enable local repository analysis and code search",
    )
    CODE_REPOSITORY_ROOTS: str = Field(
        default="",
        description="Comma-separated trusted local repository roots; blank disables repository analysis",
    )
    CODE_MAX_FILES: int = Field(
        default=5000,
        ge=100,
        le=100_000,
        description="Maximum files indexed in one repository scan",
    )
    CODE_MAX_FILE_BYTES: int = Field(
        default=1_000_000,
        ge=4096,
        le=10_000_000,
        description="Maximum source file size inspected by code tools",
    )
    CODE_MAX_RESULTS: int = Field(
        default=50,
        ge=5,
        le=500,
        description="Maximum code search results returned",
    )
    CODE_MAX_SNIPPET_CHARS: int = Field(
        default=600,
        ge=100,
        le=5000,
        description="Maximum source snippet length returned per search match",
    )
    CODE_EXCLUDED_DIRS: str = Field(
        default=".git,.hg,.svn,node_modules,.venv,venv,__pycache__,dist,build,coverage",
        description="Comma-separated generated or dependency directories excluded from indexing",
    )
    CODE_SUPPORTED_EXTENSIONS: str = Field(
        default=".py,.js,.jsx,.ts,.tsx,.java,.c,.h,.cpp,.hpp,.go,.rs,.json,.yaml,.yml,.md,.html,.css,.sql,.sh",
        description="Comma-separated source extensions accepted by repository analysis",
    )
    CODE_INDEX_CACHE_PATH: str = Field(
        default="data/code_index.json",
        description="Local metadata-only code index path",
    )

    # === Phase 8 Planning Foundation ===
    PLAN_ENABLED: bool = Field(
        default=True,
        description="Enable local structured planning and reasoning",
    )
    PLAN_DB_PATH: str = Field(
        default="data/elysia_plans.db",
        description="Local SQLite database for plans and redacted plan events",
    )
    PLAN_MAX_TASKS: int = Field(
        default=100,
        ge=1,
        le=1000,
        description="Maximum tasks in one plan",
    )
    PLAN_MAX_GOAL_CHARS: int = Field(
        default=2000,
        ge=100,
        le=10000,
        description="Maximum plan goal length",
    )
    PLAN_MAX_TEXT_CHARS: int = Field(
        default=2000,
        ge=100,
        le=10000,
        description="Maximum plan task and reasoning text length",
    )
    PLAN_MAX_RETRIES: int = Field(
        default=2,
        ge=0,
        le=5,
        description="Default maximum retries for safe plan tasks",
    )
    PLAN_DECOMPOSITION_ENABLED: bool = Field(
        default=True,
        description="Enable bounded local-Ollama goal decomposition",
    )
    PLAN_DECOMPOSITION_TIMEOUT_SECONDS: int = Field(
        default=4,
        ge=1,
        le=30,
        description="Maximum time for local goal decomposition",
    )
    PLAN_MAX_DECOMPOSED_TASKS: int = Field(
        default=12,
        ge=1,
        le=50,
        description="Maximum tasks returned by goal decomposition",
    )
    PLAN_MAX_PARALLEL_TASKS: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum independent safe tasks prepared together",
    )

    # === Phase 9 Autonomous Agents ===
    AGENTS_ENABLED: bool = Field(
        default=True,
        description="Enable the local autonomous-agent manager",
    )
    AGENTS_DB_PATH: str = Field(
        default="data/elysia_agents.db",
        description="Local SQLite database for agents, runs, and events",
    )
    AGENTS_WORKER_ENABLED: bool = Field(
        default=True,
        description="Run the bounded local agent scheduler with the backend",
    )
    AGENTS_POLL_SECONDS: int = Field(
        default=30,
        ge=5,
        le=3600,
        description="Agent scheduler poll interval in seconds",
    )
    AGENTS_MIN_INTERVAL_SECONDS: int = Field(
        default=300,
        ge=300,
        le=86400,
        description="Minimum recurring agent interval",
    )
    AGENTS_MAX_RUNTIME_SECONDS: int = Field(
        default=120,
        ge=5,
        le=3600,
        description="Maximum runtime reserved for one agent preparation",
    )
    AGENTS_MAX_ACTIVE: int = Field(
        default=3,
        ge=1,
        le=20,
        description="Maximum concurrently running agents",
    )
    AGENTS_MAX_TOOL_CALLS_PER_RUN: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum tool calls permitted per agent run",
    )
    AGENTS_MAX_NOTIFICATIONS_PER_DAY: int = Field(
        default=10,
        ge=0,
        le=100,
        description="Maximum notifications allowed per agent per UTC day",
    )

    # === Phase 10 Multimodal Input ===
    INPUT_ENABLED: bool = Field(
        default=True,
        description="Enable normalized local multimodal input ingestion",
    )
    INPUT_SAFE_ROOTS: str = Field(
        default="",
        description="Semicolon-separated local roots accepted for dropped files",
    )
    INPUT_ATTACHMENT_DIR: str = Field(
        default="data/attachments",
        description="Private local directory for copied input attachments",
    )
    INPUT_MAX_FILES_PER_DROP: int = Field(default=10, ge=1, le=50)
    INPUT_MAX_FILE_BYTES: int = Field(default=10_000_000, ge=1024, le=100_000_000)
    INPUT_MAX_TOTAL_BYTES: int = Field(default=50_000_000, ge=1024, le=500_000_000)
    INPUT_MAX_ATTACHMENTS: int = Field(default=1000, ge=10, le=10000)
    INPUT_RETENTION_HOURS: int = Field(default=24, ge=1, le=720)
    INPUT_ALLOWED_EXTENSIONS: str = Field(
        default=".txt,.md,.csv,.json,.yaml,.yml,.py,.js,.jsx,.ts,.tsx,.java,.c,.h,.cpp,.hpp,.go,.rs,.pdf,.png,.jpg,.jpeg,.webp,.gif,.wav,.mp3,.m4a,.mp4,.webm",
        description="Comma-separated allowed attachment extensions",
    )
    INPUT_PROCESSING_ENABLED: bool = Field(default=True)
    INPUT_PROCESSING_AUTO_SUMMARY: bool = Field(default=True)
    INPUT_PROCESSING_ALLOW_CLOUD: bool = Field(
        default=False,
        description="Permit attachment content to reach a configured non-local LLM provider",
    )
    INPUT_PROCESSING_MAX_TEXT_CHARS: int = Field(default=12_000, ge=100, le=100_000)
    INPUT_PROCESSING_MAX_SUMMARY_CHARS: int = Field(default=2_000, ge=100, le=10_000)
    INPUT_PROCESSING_MAX_MEMORY_PROPOSALS: int = Field(default=1, ge=0, le=3)
    INPUT_PROCESSING_POLL_SECONDS: int = Field(default=2, ge=1, le=60)

    # === Phase 3 Vision Foundation ===
    VISION_ENABLED: bool = Field(default=True)
    VISION_MAX_PIXELS: int = Field(default=16_000_000, ge=1_000_000, le=100_000_000)
    VISION_OCR_TIMEOUT_SECONDS: int = Field(default=20, ge=5, le=120)
    VISION_MAX_OCR_CHARS: int = Field(default=12_000, ge=100, le=100_000)

    # === Phase 11 Cloud Sync Foundation ===
    SYNC_ENABLED: bool = Field(default=True)
    SYNC_CLOUD_ENABLED: bool = Field(
        default=False,
        description="Enable configured cloud transport only after explicit user opt-in",
    )
    SYNC_ENCRYPTION_KEY: str = Field(
        default="",
        description="Local Fernet key for encrypted sync packages; never return or log",
    )
    SYNC_DEVICE_ID: str = Field(default="", max_length=128)
    SYNC_BACKUP_DIR: str = Field(default="data/sync_backups")
    SYNC_DB_PATH: str = Field(default="data/elysia_sync.db")
    SYNC_MAX_BACKUPS: int = Field(default=20, ge=1, le=100)
    SYNC_MAX_PACKAGE_BYTES: int = Field(default=100_000_000, ge=1_000_000, le=1_000_000_000)
    SYNC_CLOUD_ENDPOINT: str = Field(default="")
    SYNC_AUTH_TOKEN: str = Field(
        default="",
        description="Shared device-relay secret; never log, return, or include in URLs",
    )
    SYNC_ENDPOINT_ALLOWLIST: str = Field(
        default="",
        description="Semicolon-separated exact HTTPS origins allowed for cloud transport",
    )
    SYNC_ALLOW_LOOPBACK_HTTP: bool = Field(
        default=False,
        description="Allow HTTP only for an explicitly configured loopback development relay",
    )
    SYNC_REQUEST_TIMEOUT_SECONDS: int = Field(default=15, ge=3, le=120)
    SYNC_CLOCK_SKEW_SECONDS: int = Field(default=300, ge=30, le=3600)
    SYNC_REPLAY_WINDOW_SECONDS: int = Field(default=900, ge=60, le=86400)
    SYNC_MAX_PUSH_BYTES: int = Field(default=100_000_000, ge=1_000_000, le=1_000_000_000)
    SYNC_RELAY_ENABLED: bool = Field(default=False)
    SYNC_RELAY_DB_PATH: str = Field(default="data/elysia_sync_relay.db")
    SYNC_RELAY_STORAGE_DIR: str = Field(default="data/sync_relay_packages")
    SYNC_RELAY_SHARED_TOKEN: str = Field(default="")
    SYNC_RELAY_ALLOWED_DEVICES: str = Field(default="")
    SYNC_RELAY_MAX_PACKAGE_BYTES: int = Field(default=100_000_000, ge=1_000_000, le=1_000_000_000)

    # === Phase 12 Enterprise Foundation ===
    ENTERPRISE_ENABLED: bool = Field(default=True)
    ENTERPRISE_DB_PATH: str = Field(default="data/elysia_enterprise.db")
    ENTERPRISE_WORKSPACE_ID: str = Field(default="default-workspace", max_length=128)
    ENTERPRISE_WORKSPACE_NAME: str = Field(default="Elysia Local Workspace", max_length=200)
    ENTERPRISE_ADMIN_TOKEN: str = Field(
        default="",
        description="Local administration token; never log or return",
    )
    ENTERPRISE_MAX_MEMBERS: int = Field(default=100, ge=1, le=10000)
    ENTERPRISE_AUDIT_RETENTION_DAYS: int = Field(default=90, ge=1, le=3650)
    ENTERPRISE_ANALYTICS_RETENTION_DAYS: int = Field(default=90, ge=1, le=3650)
    ENTERPRISE_SESSION_TTL_MINUTES: int = Field(default=60, ge=5, le=1440)
    ENTERPRISE_SESSION_SIGNING_KEY: str = Field(
        default="",
        description="Local HMAC key for short-lived session tokens; never log or return",
    )
    ENTERPRISE_SSO_ENABLED: bool = Field(default=False)
    ENTERPRISE_SSO_ISSUER: str = Field(default="")
    ENTERPRISE_SSO_CLIENT_ID: str = Field(default="")
    ENTERPRISE_SSO_REDIRECT_URI: str = Field(default="")
    ENTERPRISE_MFA_READINESS_ENABLED: bool = Field(default=True)

    # === Logging ===

    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Logging level"
    )
    LOG_FILE: str = Field(
        default="logs/elysia.log",
        description="Log file path"
    )
    
    # === Security ===
    SECRET_KEY: str = Field(
        default="dev-secret-key-change-in-production",
        description="Secret key for encryption"
    )
    
    # === Performance ===
    MAX_CONCURRENT_REQUESTS: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum concurrent requests"
    )
    REQUEST_TIMEOUT: int = Field(
        default=30,
        ge=1,
        le=300,
        description="Request timeout in seconds"
    )
    
    # === Memory ===
    ENABLE_MEMORY: bool = Field(default=True, description="Enable local persistent memory")
    MEMORY_DB_PATH: str = Field(
        default="data/elysia_memory.db",
        description="SQLite database path for persistent memories"
    )
    MEMORY_MAX_RESULTS: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum memories injected into a chat request"
    )
    MEMORY_MAX_CONTENT_LENGTH: int = Field(
        default=1000,
        ge=50,
        le=10000,
        description="Maximum characters stored in a single memory"
    )
    MEMORY_EMBEDDING_PROVIDER: Literal["ollama", "local"] = Field(
        default="ollama",
        description="Embedding backend for semantic memory retrieval"
    )
    MEMORY_EMBEDDING_MODEL: str = Field(
        default="nomic-embed-text",
        description="Local Ollama neural embedding model"
    )
    MEMORY_EMBEDDING_TIMEOUT_MS: int = Field(
        default=750,
        ge=100,
        le=5000,
        description="Maximum embedding request time before local fallback"
    )
    MEMORY_EMBEDDING_PREWARM: bool = Field(
        default=True,
        description="Warm the neural embedding model in the background at startup"
    )
    MEMORY_EMBEDDING_VERSION: str = Field(
        default="nomic-embed-text-v1",
        description="Version tag stored with memory vectors"
    )
    MEMORY_ENCRYPTION_KEY: str = Field(
        default="",
        description="Optional Fernet key for encrypting memory content at rest"
    )
    MEMORY_RETENTION_DAYS: int = Field(
        default=0,
        ge=0,
        le=36500,
        description="Delete memories older than this many days; zero disables retention"
    )
    ENABLE_PREFERENCE_EXTRACTION: bool = Field(
        default=True,
        description="Extract only explicit stable preferences in the background"
    )

    # === Feature Flags (Future Phases) ===

    ENABLE_VISION: bool = Field(default=False, description="Enable vision (Phase 3)")
    ENABLE_PLUGINS: bool = Field(default=False, description="Enable plugins (Phase 4)")
    PLUGIN_TRUSTED_KEY_FINGERPRINTS: str = Field(
        default="",
        description="Semicolon-separated SHA-256 fingerprints of trusted Ed25519 plugin signing keys",
    )

    # === Jev ===
    JEV_DATA_DIR: str = Field(
        default="~/.jev",
        description="Directory for Jev-owned user data (contacts, notes, OAuth tokens)",
    )
    YOUTUBE_API_KEY: str = Field(
        default="",
        description="Optional free YouTube Data API key — resolves 'play X on YouTube' to the exact video",
    )
    JEV_GOOGLE_CLIENT_JSON: str = Field(
        default="",
        description="Path to the OAuth client JSON (Desktop app) for Gmail/Calendar",
    )
    JEV_GOOGLE_CLIENT_ID: str = Field(
        default="",
        description="Google OAuth client ID (alternative to JEV_GOOGLE_CLIENT_JSON)",
    )
    JEV_GOOGLE_CLIENT_SECRET: str = Field(
        default="",
        description="Google OAuth client secret (alternative to JEV_GOOGLE_CLIENT_JSON)",
    )

    # === Jev wake word (hands-free summoning) ===
    JEV_WAKE_ENABLED: bool = Field(
        default=False,
        description="Start the always-on wake-word listener with the backend "
        "(default off — the overlay toggle is the explicit opt-in)",
    )
    JEV_WAKE_MODEL: str = Field(
        default="hey_jarvis",
        description="Wake-word model: an openWakeWord model name (downloaded on "
        "first use) or a path to a custom .onnx/.tflite file",
    )
    JEV_WAKE_THRESHOLD: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Detection confidence threshold (higher = fewer false wakes)",
    )
    JEV_WAKE_COOLDOWN_S: int = Field(
        default=45,
        ge=5,
        le=300,
        description="Quiet period after a wake event so Jev's own reply can't re-trigger",
    )


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.
    
    Returns:
        Settings instance loaded from environment
    """
    return Settings()


# Convenience function for getting config
def get_config() -> Settings:
    """Alias for get_settings()."""
    return get_settings()
