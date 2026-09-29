"""Runtime configuration, loaded from environment variables (.env supported)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env", encoding="utf-8")
except Exception:  # python-dotenv is optional
    pass

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
STATIC_DIR = ROOT / "static"


def _bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None or v == "":
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    app_mode: str = field(default_factory=lambda: os.getenv("APP_MODE", "auto").strip().lower())
    hindsight_api_key: str = field(default_factory=lambda: os.getenv("HINDSIGHT_API_KEY", "").strip())
    hindsight_base_url: str = field(
        default_factory=lambda: os.getenv("HINDSIGHT_BASE_URL", "https://api.hindsight.vectorize.io").strip()
    )
    bank_prefix: str = field(default_factory=lambda: os.getenv("HINDSIGHT_BANK_PREFIX", "veilmind-").strip())
    groq_api_key: str = field(default_factory=lambda: os.getenv("GROQ_API_KEY", "").strip())
    groq_base_url: str = field(
        default_factory=lambda: os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1").strip()
    )
    llm_primary: str = field(default_factory=lambda: os.getenv("LLM_PRIMARY_MODEL", "openai/gpt-oss-120b"))
    llm_fallback: str = field(default_factory=lambda: os.getenv("LLM_FALLBACK_MODEL", "qwen/qwen3-32b"))
    llm_max_retries: int = field(default_factory=lambda: int(os.getenv("LLM_MAX_RETRIES", "3")))
    verifier_engine: str = field(default_factory=lambda: os.getenv("VERIFIER_ENGINE", "auto").strip().lower())
    # relative DB_PATH values resolve against the project folder, so it works from any working directory
    db_path: str = field(default_factory=lambda: str((ROOT / os.getenv("DB_PATH", "veilmind.sqlite3")).resolve()))
    demo_stage_delay_ms: int = field(default_factory=lambda: int(os.getenv("DEMO_STAGE_DELAY_MS", "650")))
    min_corroboration: int = field(default_factory=lambda: int(os.getenv("MIN_CORROBORATION_FOR_UNUSUAL", "2")))
    hindsight_retain_async: bool = field(default_factory=lambda: _bool("HINDSIGHT_RETAIN_ASYNC", False))

    @property
    def live_available(self) -> bool:
        return bool(self.hindsight_api_key)

    @property
    def groq_available(self) -> bool:
        return bool(self.groq_api_key)


settings = Settings()
