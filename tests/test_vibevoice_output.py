import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.data_writer import DataWriter
from app.logging import get_logger
from app.transcript import Transcript
from app.transcription import Transcription


@pytest.fixture
def pipeline(tmp_path, monkeypatch):
    """Run the real pipeline and decoder with controlled model output."""
    torch = pytest.importorskip("torch")
    pytest.importorskip("transformers")
    from transformers import VibeVoiceAsrProcessor

    from app.services.providers.vibevoice import VibeVoiceService

    writer = DataWriter(tmp_path)
    service = VibeVoiceService(upload=False, diarize=True, data_writer=writer)
    processor = object.__new__(VibeVoiceAsrProcessor)
    processor.tokenizer = Mock()

    def transcription_request(audio, prompt):
        chunk_id = 1 if audio == "chunk_1.wav" else 2
        inputs = {"input_ids": torch.tensor([[chunk_id]])}
        return Mock(**{"to.return_value": inputs})

    processor.apply_transcription_request = transcription_request
    service.processor = processor
    service.model = Mock(device="cpu", dtype=torch.float32)
    service.model.generate.side_effect = lambda input_ids: torch.cat(
        [input_ids, input_ids], dim=1
    )
    monkeypatch.setattr(service, "_unload_asr", lambda: None)
    monkeypatch.setattr(
        service,
        "_split_audio_into_chunks",
        lambda *args, **kwargs: [("chunk_1.wav", 0), ("chunk_2.wav", 180)],
    )

    audio = tmp_path / "input.wav"
    audio.touch()
    source = SimpleNamespace(
        title="Test talk",
        output_path_with_title="test-talk",
        source_file="https://www.youtube.com/watch?v=example",
        process=lambda _: str(audio),
        chapters=[],
        speakers=[],
    )
    transcript = Transcript(source)
    transcript.tmp_dir = str(tmp_path)

    engine = object.__new__(Transcription)
    engine.logger = get_logger()
    engine.nocleanup = True
    engine.metadata_writer = writer
    engine.service = service
    engine.max_retries = 2
    engine.retry_delay = 0
    engine.test_mode = False
    engine.metadata_extractor = None
    engine._correct_enabled = False
    engine._summarize_enabled = False
    engine.exporters = {}
    engine.markdown = False
    engine.github_handler = None
    engine.no_db = False
    database = Mock(is_available=True)
    monkeypatch.setattr(
        "app.transcription.get_database_service", lambda: database
    )

    return engine, transcript, processor.tokenizer, database


def segment(content):
    return {"Start": 1.0, "End": 6.0, "Speaker": 0, "Content": content}


@pytest.mark.parametrize(
    "invalid_chunk",
    [
        '[{"Start": 1.0, "End": 6.0, "Speaker": 0}]',
        '[{"Start": 1.0, "End": 6.0, "Speaker": 0, "Content": "Never closes',
        "Yes. Yes. Yes. Yes.",
    ],
)
def test_invalid_chunk_fails_pipeline_before_database_write(
    pipeline, invalid_chunk
):
    engine, transcript, tokenizer, database = pipeline
    good_chunk = json.dumps([segment("The opening sentence survives.")])
    outputs = [good_chunk, invalid_chunk]
    tokenizer.decode.side_effect = lambda ids, **kwargs: [
        outputs[ids.item() - 1]
    ]

    engine._run_pipeline(transcript)

    assert transcript.status == "failed", transcript.outputs["raw"]
    assert transcript.pipeline_state["failed_stage"] == "transcription"
    assert transcript.pipeline_state["stages"]["transcription"]["attempts"] == 2
    assert transcript.pipeline_state["stages"]["export"]["status"] == "skipped"
    assert transcript.outputs["transcription_service_output_file"] is None
    database.save_from_transcript_object.assert_not_called()


@pytest.mark.parametrize(
    "first_chunk", ["[]", json.dumps([segment("Opening remarks.")])]
)
def test_valid_chunk_is_saved_even_if_another_chunk_is_silent(
    pipeline, first_chunk
):
    engine, transcript, tokenizer, database = pipeline
    tokenizer.decode.side_effect = [
        [f"assistant\n{first_chunk}"],
        [
            json.dumps(
                [segment("The closing sentence includes café and naïve.")],
                ensure_ascii=False,
            )
        ],
    ]

    engine._run_pipeline(transcript)

    assert transcript.status == "completed"
    assert transcript.outputs["raw"].endswith(
        "The closing sentence includes café and naïve."
    )
    assert ("Opening remarks." in transcript.outputs["raw"]) == (
        first_chunk != "[]"
    )
    assert "00:03:01" in transcript.outputs["raw"]
    database.save_from_transcript_object.assert_called_once_with(transcript)


def test_empty_transcript_does_not_create_database_version(pipeline):
    engine, transcript, tokenizer, database = pipeline
    tokenizer.decode.return_value = ["[]"]

    engine._run_pipeline(transcript)

    assert transcript.status == "failed"
    assert transcript.pipeline_state["failed_stage"] == "transcription"
    database.save_from_transcript_object.assert_not_called()


def test_retry_can_save_a_complete_transcript(pipeline):
    engine, transcript, tokenizer, database = pipeline
    opening = json.dumps([segment("Opening remarks.")])
    closing = json.dumps([segment("Closing remarks.")])
    tokenizer.decode.side_effect = [
        [opening],
        ["Unstructured output"],
        [opening],
        [closing],
    ]

    engine._run_pipeline(transcript)

    assert transcript.status == "completed"
    assert transcript.pipeline_state["stages"]["transcription"]["attempts"] == 2
    assert transcript.outputs["raw"].count("Opening remarks.") == 1
    assert transcript.outputs["raw"].endswith("Closing remarks.")
    database.save_from_transcript_object.assert_called_once_with(transcript)
