import json
import os
import re

import requests

from app import application, utils
from app.config import settings
from app.data_writer import DataWriter
from app.logging import get_logger
from app.media_processor import MediaProcessor
from app.transcript import Transcript


logger = get_logger()

API_URL = "https://waves-api.smallest.ai/api/v1/pulse/get_text"


class SmallestAI:
    def __init__(self, diarize, upload, data_writer: DataWriter):
        self.diarize = diarize
        self.upload = upload
        self.data_writer = data_writer
        self.api_key = settings.SMALLEST_API_KEY
        self.language = settings.config.get("smallestai_language", "en")
        self.emotion_detection = settings.config.getboolean(
            "smallestai_emotion_detection", True
        )
        self.one_sentence_per_line = settings.config.getboolean(
            "one_sentence_per_line", True
        )
        self.max_audio_length = 3600.0  # 60 minutes
        self.processor = MediaProcessor(chunk_length=1200.0)

    def audio_to_text(self, audio_file, chunk=None):
        """Send audio to SmallestAI Pulse STT API.

        Args:
            audio_file: Path to audio file.
            chunk: Optional chunk number for logging.

        Returns:
            Parsed JSON response from the API.
        """
        logger.info(
            f"Transcribing audio {f'(chunk {chunk}) ' if chunk else ''}"
            f"to text using SmallestAI Pulse [{self.language}]..."
        )

        with open(audio_file, "rb") as f:
            file_data = f.read()

        params = {
            "language": self.language,
            "diarize": str(self.diarize).lower(),
            "word_timestamps": "true",
        }
        if self.emotion_detection:
            params["emotion_detection"] = "true"

        try:
            response = requests.post(
                API_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/octet-stream",
                },
                params=params,
                data=file_data,
                timeout=600,
            )

            if response.status_code != 200:
                raise Exception(
                    f"SmallestAI API returned status {response.status_code}: "
                    f"{response.text}"
                )

            result = response.json()

            if result.get("status") != "success":
                raise Exception(f"SmallestAI transcription failed: {result}")

            return result
        except requests.Timeout:
            raise Exception(
                "(smallestai) Request timed out. Audio may be too long — "
                "try enabling chunked transcription."
            )
        except Exception as e:
            raise Exception(
                f"(smallestai) Error transcribing audio to text: {e}"
            )

    def write_to_json_file(
        self, transcription_service_output, transcript: Transcript
    ):
        """Save raw API response to JSON file."""
        try:
            output_file = self.data_writer.write_json(
                data=transcription_service_output,
                file_path=transcript.output_path_with_title,
                filename="smallestai",
            )
            logger.info(f"(smallestai) Model output stored at: {output_file}")

            if transcript.metadata_file is not None:
                with open(transcript.metadata_file, encoding="utf-8") as file:
                    data = json.load(file)
                data["smallestai_output"] = os.path.basename(output_file)
                with open(transcript.metadata_file, "w", encoding="utf-8") as file:
                    json.dump(data, file, indent=4)

            return output_file
        except Exception as e:
            logger.error(
                f"(smallestai) Error writing JSON file for {transcript.title}: {e}"
            )
            raise

    def process_utterances(self, transcription_service_output) -> list[dict]:
        """Convert SmallestAI utterances into speaker segments.

        Args:
            transcription_service_output: Raw API response.

        Returns:
            List of speaker segment dicts with keys:
            speaker, start, end, transcript, words
        """
        utterances = transcription_service_output.get("utterances", [])
        words_list = transcription_service_output.get("words", [])

        if not utterances:
            # Fallback: no utterances, build single segment from transcription
            return [
                {
                    "speaker": "single_speaker",
                    "start": words_list[0]["start"] if words_list else 0,
                    "end": words_list[-1]["end"] if words_list else 0,
                    "transcript": transcription_service_output.get(
                        "transcription", ""
                    ),
                    "words": [
                        {
                            "punctuated_word": w.get("word", w.get("text", "")),
                            "start": w["start"],
                            "end": w["end"],
                            "speaker": 0,
                            "speaker_confidence": 1.0,
                        }
                        for w in words_list
                    ],
                }
            ]

        # Build word index for matching words to utterances
        word_idx = 0
        segments = []

        for utt in utterances:
            speaker_raw = utt.get("speaker", "speaker_0")
            # Normalize speaker ID: "speaker_0" → 0
            if isinstance(speaker_raw, str) and speaker_raw.startswith(
                "speaker_"
            ):
                speaker_id = int(speaker_raw.split("_")[-1])
            elif isinstance(speaker_raw, int):
                speaker_id = speaker_raw
            else:
                speaker_id = 0

            utt_start = utt["start"]
            utt_end = utt["end"]
            utt_text = utt.get("text", "")

            # Collect words that fall within this utterance
            segment_words = []
            while word_idx < len(words_list):
                w = words_list[word_idx]
                if w["start"] >= utt_start and w["end"] <= utt_end + 0.5:
                    segment_words.append(
                        {
                            "punctuated_word": w.get("word", w.get("text", "")),
                            "start": w["start"],
                            "end": w["end"],
                            "speaker": speaker_id,
                            "speaker_confidence": w.get("confidence", 1.0),
                        }
                    )
                    word_idx += 1
                elif w["start"] > utt_end + 0.5:
                    break
                else:
                    word_idx += 1

            segments.append(
                {
                    "speaker": speaker_id if self.diarize else "single_speaker",
                    "start": utt_start,
                    "end": utt_end,
                    "transcript": utt_text,
                    "words": segment_words,
                }
            )

        return segments

    def construct_transcript(self, segments, chapters):
        """Build final transcript text from segments with optional chapters.

        Args:
            segments: List of speaker segment dicts.
            chapters: List of chapter markers.

        Returns:
            Final transcript string.
        """
        try:
            final_transcript = ""
            chapter_index = 0 if chapters else None

            for segment in segments:
                speaker_id = segment["speaker"]
                single_speaker = speaker_id == "single_speaker"
                segment_start = segment["start"]

                # Insert chapter header if needed
                if chapter_index is not None and chapter_index < len(chapters):
                    chapter_id, chapter_start_time, chapter_title = chapters[
                        chapter_index
                    ]
                    if chapter_start_time <= segment_start:
                        final_transcript += f"\n\n## {chapter_title}\n\n"
                        chapter_index += 1

                # Add speaker timestamp
                if not single_speaker:
                    final_transcript += (
                        f"Speaker {speaker_id}: "
                        f"{utils.decimal_to_sexagesimal(segment_start)}\n\n"
                    )

                # Add transcript text
                if self.one_sentence_per_line:
                    sentences = re.split(
                        r"(?<=[.?!])\s+", segment["transcript"]
                    )
                    for sentence in sentences:
                        sentence = sentence.strip()
                        if sentence:
                            final_transcript += f"{sentence}\n"
                else:
                    final_transcript += segment["transcript"]

                final_transcript += "\n"

            return final_transcript.strip()
        except Exception as e:
            raise Exception(f"(smallestai) Error creating output format: {e}")

    def generate_srt(
        self, transcription_service_output, transcript: Transcript
    ):
        """Generate SRT subtitle file from utterances/words."""

        def format_time(seconds):
            hours = int(seconds / 3600)
            minutes = int((seconds % 3600) / 60)
            secs = int(seconds % 60)
            millis = int((seconds % 1) * 1000)
            return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

        utterances = transcription_service_output.get("utterances", [])

        # Fall back to words if no utterances
        if not utterances:
            words = transcription_service_output.get("words", [])
            # Group words into ~10-second chunks for SRT
            utterances = []
            chunk_words = []
            chunk_start = 0
            for w in words:
                if not chunk_words:
                    chunk_start = w["start"]
                chunk_words.append(w.get("word", w.get("text", "")))
                if w["end"] - chunk_start >= 10.0 or w == words[-1]:
                    utterances.append(
                        {
                            "start": chunk_start,
                            "end": w["end"],
                            "text": " ".join(chunk_words),
                        }
                    )
                    chunk_words = []

        output_file = self.data_writer.construct_file_path(
            file_path=transcript.output_path_with_title,
            filename="smallestai",
            type="srt",
        )
        logger.info(f"(smallestai) Writing SRT to {output_file}...")

        with open(output_file, "w", encoding="utf-8") as f:
            for i, utt in enumerate(utterances, 1):
                f.write(f"{i}\n")
                f.write(
                    f"{format_time(utt['start'])} --> {format_time(utt['end'])}\n"
                )
                f.write(f"{utt.get('text', '').strip()}\n\n")

        return output_file

    def finalize_transcript(self, transcript: Transcript) -> None:
        """Process API response into final transcript text."""
        try:
            if not transcript.outputs["transcription_service_output_file"]:
                raise Exception("No 'smallestai_output' found")

            with open(
                transcript.outputs["transcription_service_output_file"],
                encoding="utf-8",
            ) as f:
                transcription_service_output = json.load(f)

            segments = self.process_utterances(transcription_service_output)

            logger.info(
                f"(smallestai) Finalizing transcript "
                f"[diarization={self.diarize}, "
                f"chapters={len(transcript.source.chapters) > 0}]..."
            )

            transcript.outputs["raw"] = self.construct_transcript(
                segments, transcript.source.chapters
            )

            # Store emotion data if available
            emotions = transcription_service_output.get("emotions")
            if emotions:
                transcript.emotions = emotions
                logger.info(f"(smallestai) Emotion data captured: {emotions}")

        except Exception as e:
            raise Exception(f"(smallestai) Error finalizing transcript: {e}")

    def combine_chunk_outputs(self, all_chunks_output, overlap):
        """Combine multiple chunk outputs into a single response."""
        combined = {
            "status": "success",
            "transcription": "",
            "utterances": [],
            "words": [],
        }

        total_offset = 0.0

        for chunk_index, chunk_output in enumerate(all_chunks_output):
            transcription = chunk_output.get("transcription", "")
            utterances = chunk_output.get("utterances", [])
            words = chunk_output.get("words", [])

            # Adjust timestamps
            for utt in utterances:
                utt["start"] += total_offset
                utt["end"] += total_offset

            for w in words:
                w["start"] += total_offset
                w["end"] += total_offset

            # Skip overlapping portion for non-first chunks
            if chunk_index > 0 and utterances:
                overlap_cutoff = total_offset + overlap
                utterances = [
                    u for u in utterances if u["end"] >= overlap_cutoff
                ]
                words = [w for w in words if w["end"] >= overlap_cutoff]

            combined["transcription"] += " " + transcription
            combined["utterances"].extend(utterances)
            combined["words"].extend(words)

            # Update offset for next chunk
            total_offset += self.processor.chunk_length - overlap

        combined["transcription"] = combined["transcription"].strip()

        # Carry over emotions from last chunk (or merge)
        last_emotions = (
            all_chunks_output[-1].get("emotions") if all_chunks_output else None
        )
        if last_emotions:
            combined["emotions"] = last_emotions

        return combined

    def transcribe_in_chunks(self, transcript: Transcript):
        """Handle long audio by splitting into chunks."""
        overlap = 30.0
        chunk_files = self.processor.split_audio(
            transcript.audio_file, overlap=overlap
        )

        all_chunks_output = []
        smallestai_chunks = []

        for i, chunk_file in enumerate(chunk_files):
            chunk_output = self.audio_to_text(chunk_file, i + 1)
            all_chunks_output.append(chunk_output)

            filename = f"smallestai_chunk_{i + 1}_of_{len(chunk_files)}"
            result = self.data_writer.write_json(
                data=chunk_output,
                file_path=transcript.output_path_with_title,
                filename=filename,
            )
            smallestai_chunks.append(os.path.basename(result))

        transcription_service_output = self.combine_chunk_outputs(
            all_chunks_output, overlap=overlap
        )

        if transcript.metadata_file is not None:
            with open(transcript.metadata_file, encoding="utf-8") as file:
                data = json.load(file)
            data["smallestai_chunks"] = smallestai_chunks
            with open(transcript.metadata_file, "w", encoding="utf-8") as file:
                json.dump(data, file, indent=4)

        return transcription_service_output

    def transcribe(self, transcript: Transcript) -> None:
        """Full transcription flow."""
        try:
            import librosa

            audio_duration = librosa.get_duration(path=transcript.audio_file)

            if audio_duration > self.max_audio_length:
                logger.info(
                    f"Audio is longer than {self.max_audio_length / 60} minutes. "
                    f"Splitting into {self.processor.chunk_length / 60} min chunks."
                )
                transcription_service_output = self.transcribe_in_chunks(
                    transcript
                )
            else:
                transcription_service_output = self.audio_to_text(
                    transcript.audio_file
                )

            transcript.outputs["transcription_service_output_file"] = (
                self.write_to_json_file(
                    transcription_service_output, transcript
                )
            )

            transcript.outputs["srt_file"] = self.generate_srt(
                transcription_service_output, transcript
            )

            if self.upload:
                application.upload_file_to_s3(
                    transcript.outputs["transcription_service_output_file"]
                )

            self.finalize_transcript(transcript)
        except Exception as e:
            raise Exception(f"(smallestai) Error while transcribing: {e}")
