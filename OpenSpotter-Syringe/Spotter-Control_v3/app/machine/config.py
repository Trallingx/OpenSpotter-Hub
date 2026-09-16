"""Configuration model for the Moonraker runtime client."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping, Optional, Sequence


def _default_subscriptions() -> dict[str, tuple[str, ...]]:
    return {
        "webhooks": ("state", "state_message"),
        "toolhead": (
            "position",
            "homed_axes",
            "axis_minimum",
            "axis_maximum",
        ),
        "gcode_move": (
            "gcode_position",
            "homing_origin",
            "absolute_coordinates",
            "speed",
            "speed_factor",
        ),
        "motion_report": ("live_position", "live_velocity"),
        "bed_mesh": ("profile_name",),
        "print_stats": (
            "state",
            "filename",
            "message",
            "print_duration",
            "total_duration",
        ),
        "pause_resume": ("is_paused",),
        "idle_timeout": ("state", "printing_time"),
        "display_status": ("message",),
        "save_variables": ("variables",),
        "gcode_macro _NEEDLE_TIP_OFFSETS": None,
        "gcode_macro _OPENSPOTTER_RUNTIME": None,
        "virtual_sdcard": (
            "progress",
            "file_position",
            "file_size",
            "is_active",
        ),
    }


@dataclass(frozen=True)
class MoonrakerConfig:
    """Immutable connection and buffering configuration.

    The desktop application currently supports Python 3.8, so the runtime keeps
    all compatibility-sensitive asyncio work inside one dedicated thread.
    """

    host: str
    port: int = 7125
    scheme: str = "http"
    route_prefix: str = ""
    api_key: Optional[str] = field(default=None, repr=False)
    headers: Mapping[str, str] = field(default_factory=dict, repr=False)
    request_timeout: float = 10.0
    gcode_timeout: float = 120.0
    control_timeout: float = 15.0
    upload_timeout: float = 300.0
    emergency_timeout: float = 2.0
    connect_timeout: float = 5.0
    heartbeat: float = 20.0
    reconnect_initial: float = 0.5
    reconnect_max: float = 10.0
    reconnect_multiplier: float = 2.0
    request_queue_limit: int = 1000
    event_queue_limit: int = 2000
    console_limit: int = 500
    timing_limit: int = 500
    client_name: str = "OpenSpotter Control"
    client_version: str = "3"
    client_type: str = "desktop"
    client_url: str = "https://github.com/"
    subscriptions: Mapping[str, Optional[Sequence[str]]] = field(
        default_factory=_default_subscriptions
    )

    def __post_init__(self) -> None:
        host = str(self.host).strip()
        if not host:
            raise ValueError("Moonraker host must not be empty")
        if any(character.isspace() for character in host) or any(
            character in host for character in "/@?#"
        ):
            raise ValueError(
                "Moonraker host must contain only a host name or IP address"
            )
        if not 1 <= int(self.port) <= 65535:
            raise ValueError("Moonraker port must be between 1 and 65535")

        scheme = str(self.scheme).strip().lower()
        if scheme not in {"http", "https"}:
            raise ValueError("Moonraker scheme must be 'http' or 'https'")
        for name, value in {
            "request_timeout": self.request_timeout,
            "gcode_timeout": self.gcode_timeout,
            "control_timeout": self.control_timeout,
            "upload_timeout": self.upload_timeout,
            "emergency_timeout": self.emergency_timeout,
            "connect_timeout": self.connect_timeout,
        }.items():
            if float(value) <= 0:
                raise ValueError(f"{name} must be greater than zero")
        if float(self.heartbeat) <= 0:
            raise ValueError("Moonraker heartbeat must be greater than zero")
        if float(self.reconnect_initial) <= 0 or float(self.reconnect_max) < float(
            self.reconnect_initial
        ):
            raise ValueError("Moonraker reconnect intervals must be positive")
        if float(self.reconnect_multiplier) < 1:
            raise ValueError("Moonraker reconnect multiplier must be at least 1")
        for name, value in {
            "request_queue_limit": self.request_queue_limit,
            "event_queue_limit": self.event_queue_limit,
            "console_limit": self.console_limit,
            "timing_limit": self.timing_limit,
        }.items():
            if int(value) < 1:
                raise ValueError(f"{name} must be at least 1")

        normalized_headers = {
            str(key): str(value)
            for key, value in dict(self.headers or {}).items()
            if str(key).strip()
        }
        normalized_subscriptions = {}
        for object_name, fields in dict(self.subscriptions or {}).items():
            name = str(object_name).strip()
            if not name:
                continue
            normalized_subscriptions[name] = (
                None
                if fields is None
                else tuple(str(field_name) for field_name in fields)
            )

        object.__setattr__(self, "host", host)
        object.__setattr__(self, "port", int(self.port))
        object.__setattr__(self, "scheme", scheme)
        object.__setattr__(self, "route_prefix", self._normalize_prefix(self.route_prefix))
        for name in (
            "request_timeout",
            "gcode_timeout",
            "control_timeout",
            "upload_timeout",
            "emergency_timeout",
            "connect_timeout",
            "heartbeat",
            "reconnect_initial",
            "reconnect_max",
            "reconnect_multiplier",
        ):
            object.__setattr__(self, name, float(getattr(self, name)))
        for name in (
            "request_queue_limit",
            "event_queue_limit",
            "console_limit",
            "timing_limit",
        ):
            object.__setattr__(self, name, int(getattr(self, name)))
        object.__setattr__(self, "headers", MappingProxyType(normalized_headers))
        object.__setattr__(
            self,
            "subscriptions",
            MappingProxyType(normalized_subscriptions),
        )

    @staticmethod
    def _normalize_prefix(value: str) -> str:
        cleaned = str(value or "").strip().strip("/")
        return f"/{cleaned}" if cleaned else ""

    @property
    def base_url(self) -> str:
        return f"{self.scheme}://{self.host}:{self.port}{self.route_prefix}"

    @property
    def websocket_url(self) -> str:
        websocket_scheme = "wss" if self.scheme == "https" else "ws"
        return (
            f"{websocket_scheme}://{self.host}:{self.port}"
            f"{self.route_prefix}/websocket"
        )

    @property
    def request_headers(self) -> dict[str, str]:
        headers = dict(self.headers)
        if self.api_key and not any(
            key.lower() == "x-api-key" for key in headers
        ):
            headers["X-Api-Key"] = str(self.api_key)
        return headers

    @property
    def identify_params(self) -> dict[str, str]:
        return {
            "client_name": self.client_name,
            "version": self.client_version,
            "type": self.client_type,
            "url": self.client_url,
        }

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> "MoonrakerConfig":
        """Create a config from a JSON-compatible mapping."""
        return cls(**dict(values))
