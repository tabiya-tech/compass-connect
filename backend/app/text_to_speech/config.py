"""
The read aloud settings of the deployment, from the BACKEND_TEXT_TO_SPEECH_CONFIG environment variable: the JSON of
`speech.textToSpeech` in the config of the deployment (see config/default.json), in camelCase.
Unset or empty, read aloud is off.
"""
import json
from typing import Optional

from app.text_to_speech.types import TextToSpeechConfig

TEXT_TO_SPEECH_CONFIG_ENV_VAR = "BACKEND_TEXT_TO_SPEECH_CONFIG"


def parse_text_to_speech_config(raw: Optional[str]) -> TextToSpeechConfig:
    """
    Build the read aloud settings from the environment variable.

    :param raw: the value of BACKEND_TEXT_TO_SPEECH_CONFIG
    :raises ValueError: if the value is not valid JSON, or not valid settings. The backend does not start with a
        configuration it cannot honor.
    """
    if raw is None or not raw.strip():
        return TextToSpeechConfig()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"{TEXT_TO_SPEECH_CONFIG_ENV_VAR} is not valid JSON: {e}") from e
    return TextToSpeechConfig.model_validate(data)
