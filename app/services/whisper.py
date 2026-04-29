import json
import os

from app import application
from app.data_writer import DataWriter
from app.logging import get_logger
from app.transcript import Transcript


logger = get_logger()


class Whisper:
    def __init__(self, model, upload, data_writer: DataWriter):
        self.model = model
        self.upload = upload
        self.data_writer = data_writer
        self._whisper = None

    def _load_whisper(self):
        if self._whisper is None:
            try:
                import whisper

                self._whisper = whisper
            except ImportError:
                raise Exception(
                    "Whisper is not installed. Install with 'pip install .[whisper]'"
                )

    def audio_to_text(self, audio_file):
        logger.info(
            f"Transcribing audio to text using whisper ({self.model}) ..."
        )
        self._load_whisper()

        try:
            my_model = self._whisper.load_model(self.model)
            result = my_model.transcribe(audio_file)

            return result
        except Exception as e:
            logger.error(
                f"(wisper,{self.model}) Error transcribing audio to text: {e}"
            )
            return

    def write_to_json_file(
        self, transcription_service_output, transcript: Transcript
    ):
        transcription_service_output_file = self.data_writer.write_json(
            data=transcription_service_output,
            file_path=transcript.output_path_with_title,
            filename="whisper",
        )
        logger.info(
            f"(whisper) Model output stored at: {transcription_service_output_file}"
        )

        # Add whisper output file path to transcript's metadata file
        if transcript.metadata_file is not None:
            # Read existing content of the metadata file
            with open(transcript.metadata_file, encoding="utf-8") as file:
                data = json.load(file)
            # Add whisper output
            data["whisper_output"] = os.path.basename(
                transcription_service_output_file
            )
            # Write the updated dictionary back to the JSON file
            with open(transcript.metadata_file, "w", encoding="utf-8") as file:
                json.dump(data, file, indent=4)

        return transcription_service_output_file

    def generate_srt(self, data, transcript: Transcript):
        def format_time(time):
            hours = int(time / 3600)
            minutes = int((time % 3600) / 60)
            seconds = int(time % 60)
            milliseconds = int((time % 1) * 1000)
            return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

        output_file = self.data_writer.construct_file_path(
            file_path=transcript.output_path_with_title,
            filename="whisper",
            type="srt",
        )
        logger.info(f"(whisper) Writing srt to {output_file}...")
        with open(output_file, "w", encoding="utf-8") as f:
            for index, segment in enumerate(data["segments"]):
                f.write(f"{index + 1}\n")
                f.write(
                    f"{format_time(segment['start'])} --> {format_time(segment['end'])}\n"
                )
                f.write(f"{segment['text'].strip()}\n\n")
        return output_file

    def process_with_chapters(self, transcription_service_output, chapters):
        logger.debug("(whisper) Combining transcript with detected chapters...")
        try:
            chapters_pointer = 0
            transcript_pointer = 0
            result = ""
            segments = transcription_service_output["segments"]
            # chapters index, start time, name

            while chapters_pointer < len(chapters) and transcript_pointer < len(
                segments
            ):
                if (
                    chapters[chapters_pointer][1]
                    <= segments[transcript_pointer]["start"]
                ):
                    result = (
                        result
                        + "\n\n## "
                        + chapters[chapters_pointer][2]
                        + "\n\n"
                    )
                    chapters_pointer += 1
                else:
                    result = result + segments[transcript_pointer]["text"]
                    transcript_pointer += 1

            while transcript_pointer < len(segments):
                result = result + segments[transcript_pointer]["text"]
                transcript_pointer += 1

            return result
        except Exception as e:
            logger.error("Error combining chapters")
            logger.error(e)

    def finalize_transcript(self, transcript: Transcript) -> None:
        try:
            if not transcript.outputs["transcription_service_output_file"]:
                raise Exception("No 'whisper_output' found in JSON")
            with open(
                transcript.outputs["transcription_service_output_file"],
                encoding="utf-8",
            ) as outfile:
                transcription_service_output = json.load(outfile)

            has_chapters = len(transcript.source.chapters) > 0
            if has_chapters:
                # Source has chapters, add them to transcript
                transcript.outputs["raw"] = self.process_with_chapters(
                    transcription_service_output, transcript.source.chapters
                )
            else:
                transcript.outputs["raw"] = transcription_service_output["text"]
        except Exception as e:
            raise Exception(f"(whisper) Error finalizing transcript: {e}")

    def transcribe(self, transcript: Transcript) -> None:
        try:
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
                application.upload_file_to_s3(transcript.outputs["srt_file"])
            self.finalize_transcript(transcript)
        except Exception as e:
            raise Exception(f"(whisper) Error while transcribing: {e}")
