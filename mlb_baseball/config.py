"""Small, explicit runtime configuration for local MLB installations.

Secrets stay in environment variables.  ``mlb.toml`` is optional and holds
only ordinary operational overrides such as paths and bounded API settings.
Environment variables always win, which makes CI and one-off runs predictable.
"""

import os
import tomllib
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import cast

from dotenv import load_dotenv

load_dotenv()

DEFAULT_DOWNLOAD_DIR = Path("downloads")
DEFAULT_LOG_DIR = Path("logs")
DEFAULT_ANALYTICS_WORKERS = 8
DEFAULT_ANALYTICS_START_YEAR = 1950
DEFAULT_RETRY_ATTEMPTS = 3
DEFAULT_BACKOFF_SECONDS = 1.0
DEFAULT_REQUEST_TIMEOUT_SECONDS = 5


class ConfigError(ValueError):
    """A configuration problem that can be fixed before a run starts."""


@dataclass(frozen=True)
class Settings:
    database_url: str | None
    test_database_url: str | None
    download_dir: Path
    log_dir: Path
    analytics_workers: int
    analytics_start_year: int
    analytics_end_year: int | None
    retry_attempts: int
    backoff_seconds: float
    request_timeout_seconds: int


_TOML_KEYS = {
    "download_dir",
    "log_dir",
    "analytics_workers",
    "analytics_start_year",
    "analytics_end_year",
    "retry_attempts",
    "backoff_seconds",
    "request_timeout_seconds",
}


def _config_path(path: str | Path | None) -> Path | None:
    if path is not None:
        return Path(path)
    configured = os.environ.get("MLB_CONFIG")
    if configured:
        return Path(configured)
    default = Path("mlb.toml")
    return default if default.exists() else None


def _read_toml(path: Path | None) -> tuple[dict[str, object], Path | None]:
    if path is None:
        return {}, None
    if not path.is_file():
        raise ConfigError(
            f"config file {path} does not exist; copy mlb.toml.example or omit --config"
        )
    try:
        parsed = tomllib.loads(path.read_text())
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"cannot read config file {path}: {exc}") from exc
    values = parsed.get("mlb", parsed)
    if not isinstance(values, dict):
        raise ConfigError(f"config file {path} must contain a [mlb] table")
    unknown = set(values) - _TOML_KEYS
    if unknown:
        raise ConfigError(f"unknown config setting(s): {', '.join(sorted(unknown))}")
    return values, path.parent


def _value(values: dict[str, object], name: str, default: object) -> object:
    env_name = f"MLB_{name.upper()}"
    return os.environ.get(env_name, values.get(name, default))


def _path(value: object, name: str, base: Path | None) -> Path:
    if not isinstance(value, str):
        raise ConfigError(f"{name} must be a path string")
    path = Path(value).expanduser()
    if base is not None and not path.is_absolute():
        return (base / path).resolve()
    return path.resolve()


def _integer(value: object, name: str, minimum: int, maximum: int) -> int:
    try:
        result = int(cast(str | int | float, value))
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{name} must be an integer between {minimum} and {maximum}") from exc
    if not minimum <= result <= maximum:
        raise ConfigError(f"{name} must be between {minimum} and {maximum}")
    return result


def _number(value: object, name: str, minimum: float) -> float:
    try:
        result = float(cast(str | int | float, value))
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{name} must be a number greater than or equal to {minimum}") from exc
    if result < minimum:
        raise ConfigError(f"{name} must be greater than or equal to {minimum}")
    return result


def load_settings(path: str | Path | None = None) -> Settings:
    """Load TOML first, then apply environment overrides without side effects."""
    values, base = _read_toml(_config_path(path))
    end_value = _value(values, "analytics_end_year", "")
    end_year = (
        None
        if end_value in (None, "")
        else _integer(end_value, "analytics_end_year", 1950, date.today().year)
    )
    start_year = _integer(
        _value(values, "analytics_start_year", DEFAULT_ANALYTICS_START_YEAR),
        "analytics_start_year",
        1950,
        date.today().year,
    )
    if end_year is not None and end_year < start_year:
        raise ConfigError(
            "analytics_end_year must be greater than or equal to analytics_start_year"
        )
    return Settings(
        database_url=os.environ.get("DATABASE_URL") or None,
        test_database_url=os.environ.get("TEST_DATABASE_URL") or None,
        download_dir=_path(
            _value(values, "download_dir", str(DEFAULT_DOWNLOAD_DIR)), "download_dir", base
        ),
        log_dir=_path(_value(values, "log_dir", str(DEFAULT_LOG_DIR)), "log_dir", base),
        analytics_workers=_integer(
            _value(values, "analytics_workers", DEFAULT_ANALYTICS_WORKERS),
            "analytics_workers",
            1,
            24,
        ),
        analytics_start_year=start_year,
        analytics_end_year=end_year,
        retry_attempts=_integer(
            _value(values, "retry_attempts", DEFAULT_RETRY_ATTEMPTS), "retry_attempts", 1, 10
        ),
        backoff_seconds=_number(
            _value(values, "backoff_seconds", DEFAULT_BACKOFF_SECONDS), "backoff_seconds", 0
        ),
        request_timeout_seconds=_integer(
            _value(values, "request_timeout_seconds", DEFAULT_REQUEST_TIMEOUT_SECONDS),
            "request_timeout_seconds",
            1,
            600,
        ),
    )


def apply_settings(settings: Settings) -> None:
    """Apply the few existing module-level operational knobs used by the CLI."""
    from mlb_baseball import manifest
    from mlb_baseball.connectors import mlb_api

    manifest.DOWNLOADS_ROOT = settings.download_dir
    mlb_api.ANALYTICS_WORKERS = settings.analytics_workers
    mlb_api.ANALYTICS_REQUEST_TIMEOUT_SECONDS = settings.request_timeout_seconds
    mlb_api.ANALYTICS_RETRY_ATTEMPTS = settings.retry_attempts
    mlb_api.ANALYTICS_BACKOFF_SECONDS = settings.backoff_seconds


def database_url() -> str:
    url = load_settings().database_url
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Copy .env.example to .env, set DATABASE_URL, "
            "then run `mlb preflight`."
        )
    return url
