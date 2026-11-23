from unittest.mock import MagicMock, patch

import pytest
from google.api_core.exceptions import DeadlineExceeded, InvalidArgument, PermissionDenied, ServiceUnavailable
from google.cloud.speech_v2 import SpeechClient
from google.cloud.speech_v2.types import cloud_speech

from app.speech_to_text.adapter import CHIRP_LOCATION, RECOGNIZE_TIMEOUT_SECONDS, ChirpSpeechToTextAdapter
from app.speech_to_text.errors import SpeechToTextAdapterError
from app.speech_to_text.types import AudioUpload

_GIVEN_AUDIO = AudioUpload(content=b"webm-opus-recording", mime_type="audio/webm")


def _given_response(*results: list[str]) -> cloud_speech.RecognizeResponse:
    return cloud_speech.RecognizeResponse(results=[
        cloud_speech.SpeechRecognitionResult(
            alternatives=[cloud_speech.SpeechRecognitionAlternative(transcript=alternative) for alternative in result])
        for result in results
    ])


def _given_client(*, response: cloud_speech.RecognizeResponse | None = None,
                  error: Exception | None = None) -> MagicMock:
    client = MagicMock(spec=SpeechClient)
    if error is not None:
        client.recognize.side_effect = error
    else:
        client.recognize.return_value = response or _given_response()
    return client


_GIVEN_PROJECT_ID = "my-project"
_GIVEN_MODEL = "chirp_3"


def _given_adapter(client: MagicMock) -> ChirpSpeechToTextAdapter:
    return ChirpSpeechToTextAdapter(project_id=_GIVEN_PROJECT_ID, model=_GIVEN_MODEL, client=client)


class TestChirpSpeechToTextAdapter:
    @pytest.mark.asyncio
    async def test_sends_the_recording_to_chirp_3_in_the_given_language(self):
        # GIVEN a Google client that recognizes speech
        given_transcript = "Hello."
        given_client = _given_client(response=_given_response([given_transcript]))
        # AND a language
        given_language_code = "sw-KE"

        # WHEN a recording is recognized
        actual_transcript = await _given_adapter(given_client).recognize(audio=_GIVEN_AUDIO,
                                                                         language_code=given_language_code)

        # THEN expect the transcript
        assert actual_transcript == given_transcript
        # AND the request to use the default recognizer of the project, where Chirp 3 runs
        actual_request: cloud_speech.RecognizeRequest = given_client.recognize.call_args.kwargs["request"]
        expected_recognizer = f"projects/{_GIVEN_PROJECT_ID}/locations/{CHIRP_LOCATION}/recognizers/_"
        assert actual_request.recognizer == expected_recognizer
        # AND the model, the language, auto decoding and automatic punctuation
        assert actual_request.config.model == _GIVEN_MODEL
        assert list(actual_request.config.language_codes) == [given_language_code]
        assert "auto_decoding_config" in actual_request.config
        assert actual_request.config.features.enable_automatic_punctuation is True
        # AND the audio of the recording
        assert actual_request.content == _GIVEN_AUDIO.content
        # AND a finite deadline, so a stalled request does not hold its worker thread
        assert given_client.recognize.call_args.kwargs["timeout"] == RECOGNIZE_TIMEOUT_SECONDS

    def test_uses_the_regional_endpoint_where_chirp_3_runs(self):
        # WHEN the adapter is built without a client
        with patch("app.speech_to_text.adapter.SpeechClient") as mocked_client_class:
            ChirpSpeechToTextAdapter(project_id=_GIVEN_PROJECT_ID, model=_GIVEN_MODEL)

        # THEN expect the Google client to use the regional endpoint of the location of Chirp 3
        expected_endpoint = f"{CHIRP_LOCATION}-speech.googleapis.com"
        assert mocked_client_class.call_args.kwargs["client_options"].api_endpoint == expected_endpoint

    @pytest.mark.asyncio
    async def test_joins_the_most_likely_alternative_of_each_result_in_order(self):
        # GIVEN a response with several results, each with its most likely alternative first, and one without any
        given_first_part = "I worked"
        given_second_part = "as a carpenter."
        given_client = _given_client(response=_given_response(
            [f"{given_first_part} ", "I walked"], [], [f" {given_second_part}", "as a"]))

        # WHEN a recording is recognized
        actual_transcript = await _given_adapter(given_client).recognize(audio=_GIVEN_AUDIO, language_code="en-US")

        # THEN expect the most likely alternative of each result, trimmed, in order
        assert actual_transcript == f"{given_first_part} {given_second_part}"

    @pytest.mark.asyncio
    async def test_returns_an_empty_transcript_when_there_are_no_results(self):
        # GIVEN a response without results
        given_client = _given_client(response=_given_response())

        # WHEN a recording is recognized
        actual_transcript = await _given_adapter(given_client).recognize(audio=_GIVEN_AUDIO, language_code="en-US")

        # THEN expect an empty transcript
        assert actual_transcript == ""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("given_error", [
        ServiceUnavailable("unavailable"),
        InvalidArgument("invalid"),
        PermissionDenied("denied"),
        DeadlineExceeded("too slow"),
    ], ids=["unavailable", "invalid argument", "permission denied", "deadline exceeded"])
    async def test_maps_google_errors_to_an_adapter_error(self, given_error):
        # GIVEN a Google client that fails
        given_adapter = _given_adapter(_given_client(error=given_error))

        # WHEN a recording is recognized
        # THEN expect an adapter error with the HTTP status of the Google error
        with pytest.raises(SpeechToTextAdapterError) as actual_error:
            await given_adapter.recognize(audio=_GIVEN_AUDIO, language_code="en-US")
        assert actual_error.value.status_code == given_error.code
