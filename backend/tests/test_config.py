from __future__ import annotations

import pytest

from plecoach.config import (
    LiveKitConfigurationError,
    livekit_agent_name,
    livekit_configuration_errors,
    load_livekit_config,
)


def valid_environment() -> dict[str, str]:
    return {
        "LIVEKIT_URL": "wss://plecoach-test.livekit.cloud",
        "LIVEKIT_API_KEY": "APIplecoachtest",
        "LIVEKIT_API_SECRET": "s" * 32,
        "LIVEKIT_AGENT_NAME": "plecoach-tutor",
    }


def test_load_livekit_config_accepts_complete_settings() -> None:
    environment = valid_environment()

    config = load_livekit_config(environment)

    assert config.url == environment["LIVEKIT_URL"]
    assert config.api_key == environment["LIVEKIT_API_KEY"]
    assert config.api_secret == environment["LIVEKIT_API_SECRET"]
    assert config.agent_name == "plecoach-tutor"
    assert environment["LIVEKIT_API_SECRET"] not in repr(config)


def test_placeholder_errors_are_actionable_but_do_not_echo_secrets() -> None:
    environment = {
        "LIVEKIT_URL": "wss://your-project.livekit.cloud",
        "LIVEKIT_API_KEY": "your_livekit_api_key",
        "LIVEKIT_API_SECRET": "your_livekit_api_secret",
        "LIVEKIT_AGENT_NAME": "plecoach-tutor",
    }

    errors = livekit_configuration_errors(environment)
    message = "; ".join(errors)

    assert "LIVEKIT_URL" in message
    assert "LIVEKIT_API_KEY" in message
    assert "LIVEKIT_API_SECRET" in message
    assert environment["LIVEKIT_URL"] not in message
    assert environment["LIVEKIT_API_KEY"] not in message
    assert environment["LIVEKIT_API_SECRET"] not in message
    with pytest.raises(LiveKitConfigurationError, match="placeholder"):
        load_livekit_config(environment)


@pytest.mark.parametrize(
    ("name", "value", "expected"),
    [
        ("LIVEKIT_URL", "https://plecoach.livekit.cloud", "ws:// or wss://"),
        ("LIVEKIT_API_SECRET", "your_livekit_api_secret", "placeholder"),
        ("LIVEKIT_AGENT_NAME", "invalid agent name", "letters, numbers"),
    ],
)
def test_invalid_livekit_setting_is_rejected(
    name: str,
    value: str,
    expected: str,
) -> None:
    environment = valid_environment()
    environment[name] = value

    assert expected in "; ".join(livekit_configuration_errors(environment))


def test_short_local_development_credentials_are_allowed() -> None:
    environment = {
        "LIVEKIT_URL": "ws://livekit:7880",
        "LIVEKIT_API_KEY": "devkey",
        "LIVEKIT_API_SECRET": "secret",
        "LIVEKIT_AGENT_NAME": "plecoach-tutor",
    }

    assert livekit_configuration_errors(environment) == ()


def test_short_development_credentials_are_rejected_for_livekit_cloud() -> None:
    environment = {
        "LIVEKIT_URL": "wss://plecoach-test.livekit.cloud",
        "LIVEKIT_API_KEY": "devkey",
        "LIVEKIT_API_SECRET": "secret",
        "LIVEKIT_AGENT_NAME": "plecoach-tutor",
    }

    message = "; ".join(livekit_configuration_errors(environment))

    assert "LIVEKIT_API_KEY" in message
    assert "LIVEKIT_API_SECRET" in message
    assert "devkey" not in message
    assert "secret" not in message


def test_livekit_cloud_requires_secure_websocket_url() -> None:
    environment = valid_environment()
    environment["LIVEKIT_URL"] = "ws://plecoach-test.livekit.cloud"

    assert "must use wss://" in "; ".join(livekit_configuration_errors(environment))


def test_agent_name_is_normalized_once_for_dispatch_and_registration() -> None:
    environment = {"LIVEKIT_AGENT_NAME": "  plecoach-tutor  "}

    assert livekit_agent_name(environment) == "plecoach-tutor"
    assert load_livekit_config(
        {
            **valid_environment(),
            "LIVEKIT_AGENT_NAME": "  plecoach-tutor  ",
        }
    ).agent_name == "plecoach-tutor"
