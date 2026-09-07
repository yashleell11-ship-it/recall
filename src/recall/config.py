import os
from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True)
class Config:
    # repr=False so the key cannot ride out inside a traceback, a log line, or
    # anything that prints the config. Nothing does today — this is here so
    # that stays true after someone adds a debug print in a hurry.
    api_key: str = field(repr=False)
    base_url: str
    model: str
    db_path: str
    max_cost_usd_per_source: float
    price_input_per_mtok: float
    price_output_per_mtok: float


def load_config(env: Mapping[str, str] | None = None) -> Config:
    env = os.environ if env is None else env
    api_key = env.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "DEEPSEEK_API_KEY is not set. Put it in .env (which is gitignored)."
        )
    return Config(
        api_key=api_key,
        base_url=env.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        model=env.get("RECALL_MODEL", "deepseek-chat"),
        db_path=env.get("RECALL_DB", "recall.db"),
        max_cost_usd_per_source=float(env.get("RECALL_MAX_COST_USD", "2.0")),
        price_input_per_mtok=float(env.get("RECALL_PRICE_INPUT_PER_MTOK", "0.27")),
        price_output_per_mtok=float(env.get("RECALL_PRICE_OUTPUT_PER_MTOK", "1.10")),
    )
