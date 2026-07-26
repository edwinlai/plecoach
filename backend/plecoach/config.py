"""Validated runtime configuration shared by the API and LiveKit worker."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from urllib.parse import urlsplit

DEFAULT_AGENT_NAME = "plecoach-tutor"
DEFAULT_TTS_MODEL = "cartesia/sonic-3"
DEFAULT_TTS_VOICE = "e90c6678-f0d3-4767-9883-5d0ecf5894a8"
DEFAULT_TTS_LANGUAGE = "zh"

_AGENT_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_PLACEHOLDER_VALUES = frozenset(
    {
        "api_key",
        "apikey",
        "api_secret",
        "apisecret",
        "change_me",
        "changeme",
        "example",
        "placeholder",
        "replace_me",
        "your_api_key",
        "your_api_secret",
        "your_livekit_api_key",
        "your_livekit_api_secret",
    }
)
_PLACEHOLDER_HOSTS = frozenset(
    {
        "example.livekit.cloud",
        "project.livekit.cloud",
        "your-project.livekit.cloud",
    }
)
_CLOUD_DEVELOPMENT_KEYS = frozenset({"devkey", "dev_key"})
_CLOUD_DEVELOPMENT_SECRETS = frozenset(
    {"devsecret", "dev_secret", "secret"}
)


class LiveKitConfigurationError(ValueError):
    """Raised with secret-safe details when LiveKit settings are unusable."""


@dataclass(frozen=True, slots=True)
class LiveKitConfig:
    url: str
    api_key: str
    api_secret: str = field(repr=False)
    agent_name: str


@dataclass(frozen=True, slots=True)
class LiveKitTTSConfig:
    model: str
    voice: str
    language: str


def _normalized_placeholder_candidate(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _is_placeholder(value: str) -> bool:
    normalized = _normalized_placeholder_candidate(value)
    return (
        normalized in _PLACEHOLDER_VALUES
        or normalized.startswith("your_")
        or normalized.startswith("replace_")
        or normalized.startswith("placeholder_")
    )


def livekit_agent_name(environ: Mapping[str, str] | None = None) -> str:
    """Return the normalized dispatch/registration name shared by both services."""

    source = os.environ if environ is None else environ
    return (
        source.get("LIVEKIT_AGENT_NAME", DEFAULT_AGENT_NAME).strip()
        or DEFAULT_AGENT_NAME
    )


def livekit_tts_config(
    environ: Mapping[str, str] | None = None,
) -> LiveKitTTSConfig:
    """Load TTS settings, falling back to a native conversational Mandarin voice."""

    source = os.environ if environ is None else environ

    def configured(name: str, default: str) -> str:
        return source.get(name, default).strip() or default

    return LiveKitTTSConfig(
        model=configured("LIVEKIT_TTS_MODEL", DEFAULT_TTS_MODEL),
        voice=configured("LIVEKIT_TTS_VOICE", DEFAULT_TTS_VOICE),
        language=configured("LIVEKIT_TTS_LANGUAGE", DEFAULT_TTS_LANGUAGE),
    )


def livekit_configuration_errors(
    environ: Mapping[str, str] | None = None,
) -> tuple[str, ...]:
    """Return actionable validation errors without including credential values."""

    source = os.environ if environ is None else environ
    url = source.get("LIVEKIT_URL", "").strip()
    api_key = source.get("LIVEKIT_API_KEY", "").strip()
    api_secret = source.get("LIVEKIT_API_SECRET", "").strip()
    agent_name = livekit_agent_name(source)
    errors: list[str] = []
    is_livekit_cloud = False

    if not url:
        errors.append("LIVEKIT_URL is required")
    else:
        try:
            parsed = urlsplit(url)
            hostname = (parsed.hostname or "").lower()
        except ValueError:
            parsed = None
            hostname = ""
        is_livekit_cloud = hostname.endswith(".livekit.cloud")
        if parsed is None or parsed.scheme not in {"ws", "wss"} or not hostname:
            errors.append("LIVEKIT_URL must be a valid ws:// or wss:// URL")
        elif (
            hostname in _PLACEHOLDER_HOSTS
            or hostname.endswith(".example")
            or "placeholder" in hostname
            or hostname.startswith("your-")
        ):
            errors.append("LIVEKIT_URL uses a placeholder hostname")
        elif is_livekit_cloud and parsed.scheme != "wss":
            errors.append("LIVEKIT_URL must use wss:// for LiveKit Cloud")

    if not api_key:
        errors.append("LIVEKIT_API_KEY is required")
    elif _is_placeholder(api_key):
        errors.append("LIVEKIT_API_KEY is still a placeholder")
    elif is_livekit_cloud and (
        _normalized_placeholder_candidate(api_key) in _CLOUD_DEVELOPMENT_KEYS
        or len(api_key) < 12
    ):
        errors.append("LIVEKIT_API_KEY is not a valid LiveKit Cloud credential")

    if not api_secret:
        errors.append("LIVEKIT_API_SECRET is required")
    elif _is_placeholder(api_secret):
        errors.append("LIVEKIT_API_SECRET is still a placeholder")
    elif is_livekit_cloud and (
        _normalized_placeholder_candidate(api_secret) in _CLOUD_DEVELOPMENT_SECRETS
        or len(api_secret) < 32
    ):
        errors.append("LIVEKIT_API_SECRET is not a valid LiveKit Cloud credential")

    if not _AGENT_NAME_RE.fullmatch(agent_name):
        errors.append(
            "LIVEKIT_AGENT_NAME may contain only letters, numbers, '.', '_' or '-'"
        )

    return tuple(errors)


def load_livekit_config(
    environ: Mapping[str, str] | None = None,
) -> LiveKitConfig:
    """Load a complete LiveKit configuration or raise a safe startup error."""

    source = os.environ if environ is None else environ
    errors = livekit_configuration_errors(source)
    if errors:
        raise LiveKitConfigurationError("; ".join(errors))
    return LiveKitConfig(
        url=source["LIVEKIT_URL"].strip(),
        api_key=source["LIVEKIT_API_KEY"].strip(),
        api_secret=source["LIVEKIT_API_SECRET"].strip(),
        agent_name=livekit_agent_name(source),
    )
