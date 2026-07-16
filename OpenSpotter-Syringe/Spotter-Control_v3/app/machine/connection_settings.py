"""Persistent, UI-independent Moonraker connection settings."""

from __future__ import annotations

import json
import ipaddress
import os
import re
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional

from ..core.storage import write_json_atomic
from ..paths import CONFIG_DIR
from .config import MoonrakerConfig


DEFAULT_CONNECTION_SETTINGS_PATH = CONFIG_DIR / "config_moonraker.json"


class ConnectionSettingsError(ValueError):
    """Raised when persisted Moonraker connection settings are unusable."""


_HOST_LABEL = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")


def _normalize_host(value: Any) -> str:
    host = str(value).strip()
    if not host:
        raise ConnectionSettingsError("Moonraker host must not be empty")
    if "://" in host:
        raise ConnectionSettingsError("Host must not include http:// or https://")
    if any(character in host for character in "/@?#%"):
        raise ConnectionSettingsError(
            "Host contains URL delimiters; enter only a host name or IP address"
        )
    if any(character.isspace() for character in host):
        raise ConnectionSettingsError("Host must not contain whitespace")

    candidate = host
    bracketed = candidate.startswith("[") or candidate.endswith("]")
    if bracketed:
        if not (candidate.startswith("[") and candidate.endswith("]")):
            raise ConnectionSettingsError("IPv6 brackets are malformed")
        candidate = candidate[1:-1]

    try:
        address = ipaddress.ip_address(candidate)
    except ValueError:
        if ":" in candidate:
            raise ConnectionSettingsError("Host is not a valid IPv6 address")
        if len(candidate) > 253:
            raise ConnectionSettingsError("Host name is too long")
        labels = candidate.rstrip(".").split(".")
        if not labels or any(not _HOST_LABEL.fullmatch(label) for label in labels):
            raise ConnectionSettingsError("Host name contains invalid characters")
        return candidate.rstrip(".").lower()

    if address.version == 6:
        return f"[{address.compressed}]"
    return address.compressed


@dataclass(frozen=True)
class MoonrakerConnectionSettings:
    """Small persisted subset used to construct :class:`MoonrakerConfig`."""

    host: str = "localhost"
    port: int = 7125
    scheme: str = "http"
    route_prefix: str = ""
    api_key: Optional[str] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        host = _normalize_host(self.host)

        try:
            port = int(self.port)
        except (TypeError, ValueError) as exc:
            raise ConnectionSettingsError(
                "Moonraker port must be a whole number"
            ) from exc

        scheme = str(self.scheme).strip().lower()
        route_prefix = str(self.route_prefix or "")
        if self.api_key is not None and not isinstance(self.api_key, str):
            raise ConnectionSettingsError("API key must be text")
        api_key = (self.api_key or "").strip() or None

        try:
            normalized = MoonrakerConfig(
                host=host,
                port=port,
                scheme=scheme,
                route_prefix=route_prefix,
                api_key=api_key,
            )
        except (TypeError, ValueError) as exc:
            raise ConnectionSettingsError(str(exc)) from exc

        object.__setattr__(self, "host", normalized.host)
        object.__setattr__(self, "port", normalized.port)
        object.__setattr__(self, "scheme", normalized.scheme)
        object.__setattr__(self, "route_prefix", normalized.route_prefix)
        object.__setattr__(self, "api_key", api_key)

    @classmethod
    def from_mapping(
        cls,
        values: Mapping[str, Any],
    ) -> "MoonrakerConnectionSettings":
        """Create settings from a versioned JSON-compatible mapping."""
        if not isinstance(values, Mapping):
            raise ConnectionSettingsError(
                "Moonraker connection settings must be a JSON object"
            )
        return cls(
            host=values.get("host", "localhost"),
            port=values.get("port", 7125),
            scheme=values.get("scheme", "http"),
            route_prefix=values.get("route_prefix", ""),
            api_key=values.get("api_key") or None,
        )

    def to_persisted_mapping(self) -> dict[str, Any]:
        """Return the deliberately small on-disk schema."""
        return {
            "version": 1,
            "host": self.host,
            "port": self.port,
            "scheme": self.scheme,
            "route_prefix": self.route_prefix,
            "api_key": self.api_key or "",
        }

    def to_moonraker_config(self, **runtime_options: Any) -> MoonrakerConfig:
        """Build the full runtime config while allowing buffer/time overrides."""
        values = {
            "host": self.host,
            "port": self.port,
            "scheme": self.scheme,
            "route_prefix": self.route_prefix,
            "api_key": self.api_key,
        }
        values.update(runtime_options)
        return MoonrakerConfig(**values)


def load_connection_settings(
    path: Path = DEFAULT_CONNECTION_SETTINGS_PATH,
) -> MoonrakerConnectionSettings:
    """Load connection settings, returning safe defaults when absent."""
    config_path = Path(path)
    if not config_path.exists():
        return MoonrakerConnectionSettings()

    try:
        with config_path.open("r", encoding="utf-8") as config_file:
            payload = json.load(config_file)
    except (OSError, json.JSONDecodeError) as exc:
        raise ConnectionSettingsError(
            "Moonraker connection settings could not be read"
        ) from exc

    try:
        return MoonrakerConnectionSettings.from_mapping(payload)
    except (TypeError, ValueError) as exc:
        if isinstance(exc, ConnectionSettingsError):
            raise
        raise ConnectionSettingsError(
            "Moonraker connection settings are invalid"
        ) from exc


def save_connection_settings(
    settings: MoonrakerConnectionSettings,
    path: Path = DEFAULT_CONNECTION_SETTINGS_PATH,
) -> Path:
    """Atomically save settings without writing their values to logs."""
    if not isinstance(settings, MoonrakerConnectionSettings):
        raise TypeError("settings must be MoonrakerConnectionSettings")

    config_path = Path(path)
    write_json_atomic(
        config_path,
        settings.to_persisted_mapping(),
        replace=os.replace,
    )
    try:
        os.chmod(config_path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    return config_path
