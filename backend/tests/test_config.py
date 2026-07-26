from __future__ import annotations

import pytest

from plecoach.config import (
    DEFAULT_TTS_LANGUAGE,
    DEFAULT_TTS_MODEL,
    DEFAULT_TTS_VOICE,
    LiveKitConfigurationError,
    livekit_agent_name,
    livekit_configuration_errors,
    livekit_tts_config,
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


def test_tts_defaults_to_native_conversational_mandarin_voice() -> None:
    config = livekit_tts_config({})

    assert config.model == "cartesia/sonic-3" == DEFAULT_TTS_MODEL
    assert config.voice == "e90c6678-f0d3-4767-9883-5d0ecf5894a8"
    assert config.voice == DEFAULT_TTS_VOICE
    assert config.language == "zh" == DEFAULT_TTS_LANGUAGE


def test_tts_settings_allow_trimmed_environment_overrides() -> None:
    config = livekit_tts_config(
        {
            "LIVEKIT_TTS_MODEL": " custom/model ",
            "LIVEKIT_TTS_VOICE": " custom-voice ",
            "LIVEKIT_TTS_LANGUAGE": " zh-CN ",
        }
    )

    assert config.model == "custom/model"
    assert config.voice == "custom-voice"
    assert config.language == "zh-CN"


def test_blank_tts_settings_fall_back_to_safe_defaults() -> None:
    config = livekit_tts_config(
        {
            "LIVEKIT_TTS_MODEL": " ",
            "LIVEKIT_TTS_VOICE": "",
            "LIVEKIT_TTS_LANGUAGE": "\t",
        }
    )

    assert config.model == DEFAULT_TTS_MODEL
    assert config.voice == DEFAULT_TTS_VOICE
    assert config.language == DEFAULT_TTS_LANGUAGE
