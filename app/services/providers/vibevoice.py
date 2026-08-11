import json
import os
import re

import torch

from app import application, utils
from app.config import settings
from app.data_writer import DataWriter
from app.logging import get_logger
from app.transcript import Transcript

from app.services.providers.base import BaseTranscriptionService

logger = get_logger()

MODEL_ID = "microsoft/VibeVoice-ASR-HF"


def _get_device():
    """Detect the best available device. Forced to 'cpu' for VibeVoice to avoid MPS memory issues."""
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


class VibeVoiceService(BaseTranscriptionService):
    PROVIDER_NAME = "vibevoice"

    def __init__(self, upload, diarize, data_writer: DataWriter):
        self.upload = upload
        self.diarize = diarize
        self.data_writer = data_writer
        self.one_sentence_per_line = settings.config.getboolean(
            "one_sentence_per_line", True
        )

        self.model_id = settings.config.get("vibevoice_model", MODEL_ID)
        self.device = _get_device()
        self.model = None
        self.processor = None

    def _load_asr(self):
        if self.model is not None:
            return

        logger.info(f"(vibevoice) Loading model '{self.model_id}' with device_map={self.device} ...")
        # pyrefly: ignore [missing-import]
        from transformers import AutoProcessor, VibeVoiceAsrForConditionalGeneration

        self.processor = AutoProcessor.from_pretrained(
            self.model_id, token=settings.HF_TOKEN
        )
        self.model = VibeVoiceAsrForConditionalGeneration.from_pretrained(
            self.model_id,
            device_map=self.device,
            token=settings.HF_TOKEN,
        )
        logger.info(
            f"(vibevoice) Model loaded on {self.model.device} with dtype {self.model.dtype}"
        )

    def _unload_asr(self):
        if self.model is None:
            return

        logger.info("(vibevoice) Unloading model from GPU...")
        import gc
        import torch

        del self.model
        del self.processor
        self.model = None
        self.processor = None
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        elif torch.backends.mps.is_available():
            torch.mps.empty_cache()
        logger.info("(vibevoice) Model unloaded.")

    def __str__(self):
        model_id = settings.config.get("vibevoice_model", MODEL_ID)
        return f"VibeVoice(model={model_id}, diarize={self.diarize})"

    @classmethod
    def from_config(cls, config: dict, metadata_writer: DataWriter) -> "VibeVoiceService":
        return cls(
            upload=config.get("upload", False),
            diarize=config.get("diarize", False),
            data_writer=metadata_writer,
        )

    def audio_to_text(self, audio_file: str, context_prompt: str = None) -> list[dict]:
        """Run VibeVoice inference on a local audio file.

        Returns a list of dicts: {"Start", "End", "Speaker", "Content"}
        """
        logger.info(
            f"(vibevoice) Transcribing audio: {os.path.basename(audio_file)} ..."
        )

        inputs = self.processor.apply_transcription_request(
            audio=audio_file,
            prompt=context_prompt,
        ).to(self.model.device, self.model.dtype)

        with torch.no_grad():
            output_ids = self.model.generate(**inputs)

        generated_ids = output_ids[:, inputs["input_ids"].shape[1]:]

        parsed = self.processor.decode(generated_ids, return_format="parsed")[0]

        # Fallback: if parsing fails (returns a raw string), return empty list
        if isinstance(parsed, str):
            logger.warning(
                "(vibevoice) Could not parse structured output — falling back to raw text."
            )
            raw_text = self.processor.decode(
                generated_ids, return_format="transcription_only"
            )[0]
            return [{"Start": 0, "End": 0, "Speaker": 0, "Content": raw_text}]

        return parsed  # list of {"Start", "End", "Speaker", "Content"}

    def write_to_json_file(self, utterances: list, transcript: Transcript) -> str:
        """Save raw VibeVoice output to a JSON file."""
        try:
            output_file = self.data_writer.write_json(
                data={"utterances": utterances},
                file_path=transcript.output_path_with_title,
                filename="vibevoice",
            )
            logger.info(f"(vibevoice) Model output stored at: {output_file}")

            if transcript.metadata_file is not None:
                with open(transcript.metadata_file) as f:
                    data = json.load(f)
                data["vibevoice_output"] = os.path.basename(output_file)
                with open(transcript.metadata_file, "w") as f:
                    json.dump(data, f, indent=4)

            return output_file
        except Exception as e:
            logger.error(
                f"(vibevoice) Error writing JSON file for {transcript.title}: {e}"
            )
            raise

    def construct_transcript(self, utterances: list, chapters: list) -> str:
        """Build final transcript text from VibeVoice utterances."""
        try:
            final_transcript = ""
            chapter_index = 0 if chapters else None

            for segment in utterances:
                speaker_id = segment.get("Speaker", 0)
                segment_start = segment.get("Start", 0)
                content = segment.get("Content", "").strip()

                # Insert chapter header if needed
                if chapter_index is not None and chapter_index < len(chapters):
                    _, chapter_start_time, chapter_title = chapters[chapter_index]
                    if chapter_start_time <= segment_start:
                        final_transcript += f"\n\n## {chapter_title}\n\n"
                        chapter_index += 1

                # Add speaker timestamp line if diarizing
                if self.diarize:
                    final_transcript += (
                        f"Speaker {speaker_id}: "
                        f"{utils.decimal_to_sexagesimal(segment_start)}\n\n"
                    )

                # Add transcript text
                if self.one_sentence_per_line:
                    sentences = re.split(r"(?<=[.?!])\s+", content)
                    for sentence in sentences:
                        sentence = sentence.strip()
                        if sentence:
                            final_transcript += f"{sentence}\n"
                else:
                    final_transcript += content

                final_transcript += "\n"

            return final_transcript.strip()
        except Exception as e:
            raise Exception(f"(vibevoice) Error creating output format: {e}")

    def finalize_transcript(self, transcript: Transcript) -> None:
        """Process VibeVoice output into final transcript text."""
        try:
            if not transcript.outputs.get("transcription_service_output_file"):
                raise Exception("(vibevoice) No output file found.")

            with open(transcript.outputs["transcription_service_output_file"]) as f:
                data = json.load(f)

            utterances = data.get("utterances", [])

            logger.info(
                f"(vibevoice) Finalizing transcript "
                f"[diarization={self.diarize}, "
                f"chapters={len(transcript.source.chapters) > 0}, "
                f"utterances={len(utterances)}]..."
            )

            transcript.outputs["raw"] = self.construct_transcript(
                utterances, transcript.source.chapters
            )
        except Exception as e:
            raise Exception(f"(vibevoice) Error finalizing transcript: {e}")

    def _split_audio_into_chunks(self, audio_file: str, chunk_length_s: float) -> list[tuple[str, float]]:
        """Split audio into fixed-length chunks. Private to VibeVoiceService."""
        import librosa
        import soundfile as sf
        
        output_dir = os.path.splitext(audio_file)[0] + "_vibevoice_chunks"
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        audio, sr = librosa.load(audio_file, sr=None)
        duration = librosa.get_duration(y=audio, sr=sr)
        
        chunk_paths = []
        chunk_start = 0.0
        chunk_counter = 1

        while chunk_start < duration:
            chunk_end = min(chunk_start + chunk_length_s, duration)
            chunk_audio = audio[int(chunk_start * sr) : int(chunk_end * sr)]
            chunk_path = os.path.join(output_dir, f"chunk_{chunk_counter}.wav")
            sf.write(chunk_path, chunk_audio, sr)
            
            chunk_paths.append((chunk_path, chunk_start))
            chunk_start = chunk_end
            chunk_counter += 1

        return chunk_paths

    def transcribe(self, transcript: Transcript) -> None:
        """Full VibeVoice transcription flow."""
        try:
            # Build context prompt from title + speakers (Bitcoin hotwords)
            context_parts = []
            if transcript.source.title:
                context_parts.append(transcript.source.title)
            if transcript.source.speakers:
                context_parts.append(
                    "Speakers: " + ", ".join(transcript.source.speakers)
                )
            context_prompt = ". ".join(context_parts) if context_parts else None

            chunk_length = settings.config.getint("vibevoice_chunk_length", 180)
            chunks = self._split_audio_into_chunks(transcript.audio_file, chunk_length)

            self._load_asr()
            all_utterances = []
            
            for chunk_path, start_offset in chunks:
                utterances = self.audio_to_text(
                    chunk_path,
                    context_prompt=context_prompt,
                )
                for u in utterances:
                    u["Start"] += start_offset
                    u["End"] += start_offset
                all_utterances.extend(utterances)
                
            self._unload_asr()

            transcript.outputs["transcription_service_output_file"] = (
                self.write_to_json_file(all_utterances, transcript)
            )

            if self.upload:
                application.upload_file_to_s3(
                    transcript.outputs["transcription_service_output_file"]
                )

            self.finalize_transcript(transcript)

        except Exception as e:
            self._unload_asr()
            raise Exception(f"(vibevoice) Error while transcribing: {e}")

