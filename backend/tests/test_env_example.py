"""Smoke tests for the Phase 0 scaffold.

They protect two rules that must never break: every required environment
variable is documented, and no real secret is ever written in .env.example.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

REQUIRED_VARS = [
    "ENV",
    "DATABASE_URL",
    "REDIS_URL",
    "JWT_SECRET",
    "ACCESS_TOKEN_MINUTES",
    "REFRESH_TOKEN_DAYS",
    "FRONTEND_ORIGIN",
    "RUN_EMBEDDED_WORKER",
    "GROQ_API_KEY",
    "GROQ_MODEL",
    "TELEGRAM_BOT_TOKEN",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USER",
    "SMTP_PASSWORD",
    "SMTP_FROM",
]

# These must stay empty in .env.example. Real values belong only in .env.
SECRET_VARS = ["JWT_SECRET", "GROQ_API_KEY", "TELEGRAM_BOT_TOKEN", "SMTP_PASSWORD"]


def read_env_example() -> dict[str, str]:
    values: dict[str, str] = {}
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    for raw in text.splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            name, value = line.split("=", 1)
            values[name.strip()] = value.strip()
    return values


def test_env_example_lists_every_required_variable():
    names = read_env_example()
    missing = [name for name in REQUIRED_VARS if name not in names]
    assert not missing, f"Missing from .env.example: {missing}"


def test_env_example_has_no_secret_values():
    values = read_env_example()
    filled = [name for name in SECRET_VARS if values.get(name)]
    assert not filled, f"Secret values must be blank in .env.example: {filled}"


def test_gitignore_blocks_env_first():
    lines = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    rules = [line.strip() for line in lines if line.strip() and not line.startswith("#")]
    assert rules[0] == ".env"
