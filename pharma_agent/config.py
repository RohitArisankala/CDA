from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent


def load_app_env() -> None:
    env_path = BASE_DIR / ".env"
    example_path = BASE_DIR / ".env.example"

    if env_path.exists():
        load_dotenv(env_path)
    elif example_path.exists():
        load_dotenv(example_path)
    else:
        load_dotenv()
