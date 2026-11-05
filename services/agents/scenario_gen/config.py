"""Settings read from environment variables (and from services/agents/.env when it exists).

The OpenRouter key is read from OPENROUTER_API_KEY only. Never write it in the code or commit it.
"""
import os
from dataclasses import dataclass
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def load_env_file(path: Path = ENV_FILE) -> None:
    """Tiny .env loader (no dependency). Real environment variables win over the file."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    openrouter_api_key: str | None
    openrouter_model: str
    openrouter_base_url: str
    llm_timeout: float
    store_path: str | None  # JSON-lines file; None = memory only
    sim_intents_path: str | None  # the Customer Sim's intents.json, to align problem_type keys

    @classmethod
    def from_env(cls) -> "Settings":
        load_env_file()
        return cls(
            openrouter_api_key=os.environ.get("OPENROUTER_API_KEY") or None,
            openrouter_model=os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini"),
            openrouter_base_url=os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            llm_timeout=float(os.environ.get("OPENROUTER_TIMEOUT", "25")),
            store_path=os.environ.get("SCENARIO_STORE_PATH") or None,
            sim_intents_path=os.environ.get("CUSTOMER_SIM_INTENTS_PATH") or None,
        )
