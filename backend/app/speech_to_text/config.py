"""
The voice input settings of the deployment, from the BACKEND_SPEECH_TO_TEXT_CONFIG environment variable: the JSON of
`speech.speechToText` in the config of the deployment (see config/default.json), in camelCase.
Unset or empty, voice input is off.
"""
import json
from typing import Optional

from app.speech_to_text.types import SpeechToTextConfig

SPEECH_TO_TEXT_CONFIG_ENV_VAR = "BACKEND_SPEECH_TO_TEXT_CONFIG"


def parse_speech_to_text_config(raw: Optional[str]) -> SpeechToTextConfig:
    """
    Build the voice input settings from the environment variable.

    :param raw: the value of BACKEND_SPEECH_TO_TEXT_CONFIG
    :raises ValueError: if the value is not valid JSON, or not valid settings. The backend does not start with a
        configuration it cannot honor.
    """
    if raw is None or not raw.strip():
        return SpeechToTextConfig()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"{SPEECH_TO_TEXT_CONFIG_ENV_VAR} is not valid JSON: {e}") from e
    return SpeechToTextConfig.model_validate(data)
