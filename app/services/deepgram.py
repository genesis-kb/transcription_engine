import json
import mimetypes
import os
import re

import deepgram
import librosa

from app import application, utils
from app.config import settings
from app.data_writer import DataWriter
from app.logging import get_logger
from app.media_processor import MediaProcessor
from app.transcript import Transcript
from app.types import (
    DigitalPaperEditFormat,
    DigitalPaperEditParagraph,
    DigitalPaperEditWord,
    Sentence,
    SpeakerSegment,
    SpeakerSegmentWithSentences,
)


logger = get_logger()


class Deepgram:
    def __init__(self, summarize, diarize, upload, data_writer: DataWriter):
        self.summarize = summarize
        self.diarize = diarize
        self.upload = upload
        self.data_writer = data_writer
        self.one_sentence_per_line = settings.config.getboolean(
            "one_sentence_per_line", True
        )
        self.dpe_output = settings.config.getboolean("dpe_output", True)
        self.dev_mode = False  # Extra capabilities during development mode
        self.max_audio_length = 3600.0  # 60 minutes in seconds
        self.processor = MediaProcessor(chunk_length=1200.0)
        self.api_key = settings.DEEPGRAM_API_KEY

    def audio_to_text(self, audio_file, chunk=None):
        language = settings.config.get("language", "en")
        logger.info(
            f"Transcribing audio {f'(chunk {chunk}) ' if chunk else ''}to text using deepgram[{language}]..."
        )
        try:
            dg_client = deepgram.Deepgram(self.api_key)

            with open(audio_file, "rb") as audio:
                mimeType = mimetypes.MimeTypes().guess_type(audio_file)[0]
                source = {"buffer": audio, "mimetype": mimeType}
                response = dg_client.transcription.sync_prerecorded(
                    source,
                    {
                        "punctuate": True,
                        "speaker_labels": True,
                        "diarize": self.diarize,
                        "smart_formatting": True,
                        "summarize": self.summarize,
                        "model": "whisper-large",
                        "language": language,
                    },
                )
                audio.close()
            return response
        except Exception as e:
            raise Exception(f"(deepgram) Error transcribing audio to text: {e}")

    def write_to_json_file(
        self, transcription_service_output, transcript: Transcript
    ):
        try:
            transcription_service_output_file = self.data_writer.write_json(
                data=transcription_service_output,
                file_path=transcript.output_path_with_title,
                filename="deepgram",
            )
            logger.info(
                f"(deepgram) Model output stored at: {transcription_service_output_file}"
            )

            # Add deepgram output file path to transcript's metadata file
            if transcript.metadata_file is not None:
                # Read existing content of the metadata file
                with open(transcript.metadata_file, encoding="utf-8") as file:
                    data = json.load(file)
                # Add deepgram output
                data["deepgram_output"] = os.path.basename(
                    transcription_service_output_file
                )
                # Write the updated dictionary back to the JSON file
                with open(transcript.metadata_file, "w", encoding="utf-8") as file:
                    json.dump(data, file, indent=4)

            return transcription_service_output_file
        except Exception as e:
            logger.error(
                f"(deepgram) Error writing JSON file for {transcript.title}: {e}"
            )
            raise

    def process_summary(self, transcript: Transcript):
        if not transcript.outputs["transcription_service_output_file"]:
            raise Exception("No 'deepgram_output' found in JSON")
        with open(
            transcript.outputs["transcription_service_output_file"],
            encoding="utf-8",
        ) as outfile:
            transcription_service_output = json.load(outfile)

        try:
            summaries = transcription_service_output["results"]["channels"][0][
                "alternatives"
            ][0]["summaries"]
            summary = ""
            for x in summaries:
                summary = summary + " " + x["summary"]
            return summary.strip(" ")
        except Exception as e:
            logger.error(f"Error getting summary: {e}")

    def process_segments(
        self, transcription_service_output, diarization
    ) -> list[SpeakerSegment]:
        try:
            words = transcription_service_output["results"]["channels"][0][
                "alternatives"
            ][0]["words"]
            segments = []
            current_segment = None

            for word in words:
                speaker_id = (
                    word["speaker"] if diarization else "single_speaker"
                )
                speaker_text = word["punctuated_word"]
                if speaker_id != current_segment:
                    # change of speaker
                    current_segment = speaker_id
                    segments.append(
                        {
                            "speaker": speaker_id,
                            "start": word["start"],
                            "end": word["end"],
                            "transcript": "",
                            "words": [],
                        }
                    )

                segments[-1]["transcript"] += f"{speaker_text} "
                segments[-1]["words"].append(word)
                segments[-1]["end"] = word["end"]

            for segment in segments:
                segment["transcript"] = segment["transcript"].strip()

            return segments
        except Exception as e:
            raise Exception(
                f"(deepgram) Error constructing speaker segments: {e}"
            )

    def break_segments_into_sentences(
        self, segments
    ) -> list[SpeakerSegmentWithSentences]:
        result = []
        # Define the sentence splitting pattern
        abbreviation_pattern = r"(?<!\w\.\w.)(?<![A-Z][a-z]\.)"
        sentence_end_pattern = r"(?<=\.|\?|…|-)\s"
        sentence_split_pattern = f"{abbreviation_pattern}{sentence_end_pattern}"
        try:
            for segment in segments:
                # Split the segment into sentences
                sentences = re.split(
                    sentence_split_pattern, segment["transcript"]
                )

                segment_data = {
                    "speaker": segment["speaker"],
                    "transcript": segment["transcript"],
                    "start": segment["start"],
                    "end": segment["end"],
                    "sentences": [],
                }

                word_index = 0

                for sentence in sentences:
                    sentence_words = sentence.split()
                    sentence_data = {
                        "transcript": sentence,
                        "start": segment["words"][word_index]["start"],
                        "end": segment["words"][
                            word_index + len(sentence_words) - 1
                        ]["end"],
                        "words": segment["words"][
                            word_index : word_index + len(sentence_words)
                        ],
                    }

                    word_index += len(sentence_words)
                    segment_data["sentences"].append(sentence_data)

                result.append(segment_data)

            return result
        except Exception as e:
            logger.error(
                f"(deepgram) Error breaking segments into sentences: {e}"
            )
            raise

    def adjust_chapter_timestamps(
        self, speaker_segements_with_sentences, chapters
    ):
        """Adjust the given chapter timestamps to prevent mid-sentence line break"""

        def find_sentence_for_timestamp(
            speaker_segements_with_sentences, timestamp
        ):
            for speaker_data in speaker_segements_with_sentences:
                for sentence_data in speaker_data["sentences"]:
                    if (
                        sentence_data["start"]
                        <= timestamp
                        <= sentence_data["end"]
                    ):
                        return sentence_data
            return None

        def adjust_timestamp(original_timestamp, sentence_start, sentence_end):
            midpoint = (sentence_start + sentence_end) / 2
            return (
                sentence_end
                if original_timestamp >= midpoint
                else sentence_start
            )

        adjusted_chapters = []

        try:
            for chapter in chapters:
                chapter_start_time = chapter[1]
                chapter_sentence = find_sentence_for_timestamp(
                    speaker_segements_with_sentences, chapter_start_time
                )

                if chapter_sentence:
                    adjusted_start_time = adjust_timestamp(
                        chapter_start_time,
                        chapter_sentence["start"],
                        chapter_sentence["end"],
                    )
                    adjusted_chapter = [
                        chapter[0],
                        adjusted_start_time,
                    ] + chapter[2:]
                    adjusted_chapters.append(adjusted_chapter)
                else:
                    adjusted_chapters.append(chapter)

            return adjusted_chapters
        except Exception as e:
            logger.error(f"(deepgram) Error adjusting chapter timestamps: {e}")
            raise

    def fix_broken_sentences(
        self, speaker_segments_with_sentences: list[SpeakerSegmentWithSentences]
    ) -> list[SpeakerSegmentWithSentences]:
        """
        Fixes broken sentences between consecutive speaker segments by combining them with the following segment's initial sentence.
        Broken sentences are identified by the absence of proper punctuation marks at the end. Attribution is based on sentence length,
        with longer sentences attributed to the current speaker and shorter ones to the next speaker.
        """

        def sentence_is_broken(
            last_sentence_current: Sentence, first_sentence_next: Sentence
        ):
            """
            Helper method to check if a Sentence is broken.
            Sentence is broken if the last character of the sentence is not one of the accepted punctuation marks.
            """
            confidence_threshold = (
                0.0  # 0.0 means that confidence_threshold is disabled
            )
            last_char = last_sentence_current["transcript"][-1]
            if last_char not in [".", "?", ",", "…"]:
                confidence_difference = abs(
                    last_sentence_current["words"][-1]["speaker_confidence"]
                    - first_sentence_next["words"][0]["speaker_confidence"]
                )
                if confidence_difference > confidence_threshold:
                    return True

            return False

        def update_segment_attributes(segment: SpeakerSegmentWithSentences):
            """
            Updates the attributes of a SpeakerSegmentWithSentences object to reflect changes in its sentences list.
            This method recalculates and sets the 'transcript', 'start', and 'end' attributes based on the current
            sentences within the segment.
            """
            if segment["sentences"]:
                # Update the transcript by concatenating all sentence transcripts
                segment["transcript"] = " ".join(
                    sentence["transcript"] for sentence in segment["sentences"]
                )

                # Update the start and end times based on the sentences
                segment["start"] = segment["sentences"][0]["start"]
                segment["end"] = segment["sentences"][-1]["end"]

        def add_band_aid_word(last_sentence_current, first_sentence_next):
            """
            Creates a "band-aid" word entry to indicate the point of sentence merging in development mode.
            This method calculates the difference in speaker confidence between the last word of the current sentence
            and the first word of the next sentence. The band-aid word is formatted as '[bs={difference}]', where
            'difference' is the calculated speaker confidence difference. This helps in visually identifying the
            location and degree of modification when sentences are combined due to the broken sentence heuristic.
            """
            # Calculate the speaker confidence difference
            confidence_difference = abs(
                last_sentence_current["words"][-1]["speaker_confidence"]
                - first_sentence_next["words"][0]["speaker_confidence"]
            )
            # Create a band-aid word entry
            band_aid_word = {
                "punctuated_word": f"[bs={confidence_difference:.3f}]",
                "speaker_confidence": 0,  # Or some other appropriate default value
            }
            return band_aid_word

        try:
            i = 0
            while i < len(speaker_segments_with_sentences) - 1:
                current_segment = speaker_segments_with_sentences[i]
                next_segment = speaker_segments_with_sentences[i + 1]

                if current_segment["sentences"]:
                    last_sentence_current = current_segment["sentences"][-1]
                    first_sentence_next = next_segment["sentences"][0]

                    if sentence_is_broken(
                        last_sentence_current, first_sentence_next
                    ):
                        combined_sentence = {
                            "transcript": last_sentence_current["transcript"]
                            + " "
                            + first_sentence_next["transcript"],
                            "start": last_sentence_current["start"],
                            "end": first_sentence_next["end"],
                            "words": last_sentence_current["words"]
                            + first_sentence_next["words"],
                            "fixed_by_heuristic": "broken-sentence",
                        }
                        # Add the band-aid word if in dev mode
                        if self.dev_mode:
                            band_aid_word = add_band_aid_word(
                                last_sentence_current, first_sentence_next
                            )
                            # Insert the band-aid word at the junction of the two sentences
                            combined_sentence["words"] = (
                                last_sentence_current["words"]
                                + [band_aid_word]
                                + first_sentence_next["words"]
                            )

                        # Determine which segment is longer
                        if (
                            last_sentence_current["end"]
                            - last_sentence_current["start"]
                            > first_sentence_next["end"]
                            - first_sentence_next["start"]
                        ):
                            # Attribute the broken sentence to the current speaker
                            current_segment["sentences"][-1] = combined_sentence
                            # Remove the first sentence of the next segment
                            next_segment["sentences"].pop(0)
                        else:
                            # Attribute the broken sentence to the next speaker
                            next_segment["sentences"][0] = combined_sentence
                            # Remove the last sentence of the current segment
                            current_segment["sentences"].pop()

                        update_segment_attributes(current_segment)
                        update_segment_attributes(next_segment)

                # Check if next_segment is empty and remove it if it is
                if not next_segment["sentences"]:
                    speaker_segments_with_sentences.pop(i + 1)
                else:
                    i += 1

            # Remove any empty speaker segments from the list
            speaker_segments_with_sentences = [
                segment
                for segment in speaker_segments_with_sentences
                if segment["sentences"]
            ]

            # Merge consecutive segments with the same speaker
            i = 0
            while i < len(speaker_segments_with_sentences) - 1:
                current_segment = speaker_segments_with_sentences[i]
                next_segment = speaker_segments_with_sentences[i + 1]
                if current_segment["speaker"] == next_segment["speaker"]:
                    current_segment["transcript"] += (
                        " " + next_segment["transcript"]
                    )
                    current_segment["end"] = next_segment["end"]
                    current_segment["sentences"].extend(
                        next_segment["sentences"]
                    )
                    speaker_segments_with_sentences.pop(i + 1)
                else:
                    i += 1

            return speaker_segments_with_sentences
        except Exception as e:
            logger.error(f"(deepgram) Error fixing broken sentences: {e}")
            raise

    def transform_to_digital_paper_edit_format(
        self, segments: list[SpeakerSegmentWithSentences], chapters: list[list]
    ) -> DigitalPaperEditFormat:
        words: list[DigitalPaperEditWord] = []
        paragraphs: list[DigitalPaperEditParagraph] = []

        word_id = 0  # Unique identifier for each word
        chapter_index = 0 if chapters else None
        next_chapter_title = None
        next_chapter_start_time = float("inf")

        if chapter_index is not None and chapter_index < len(chapters):
            (
                _,
                next_chapter_start_time,
                next_chapter_title,
            ) = chapters[chapter_index]

        for segment in segments:
            segment_start = segment["start"]
            segment_end = segment["end"]
            segment_speaker = f"Speaker {segment['speaker']}"
            sentences = segment["sentences"]

            current_sentence_index = 0
            paragraph_start = segment_start
            chapter_title = None

            while current_sentence_index < len(sentences):
                sentence = sentences[current_sentence_index]
                sentence_start = sentence["start"]
                sentence["end"]

                # Check if a new chapter starts before this sentence
                if (
                    chapter_index is not None
                    and next_chapter_start_time <= sentence_start
                ):
                    if paragraph_start < next_chapter_start_time:
                        # Prepare paragraph data
                        paragraph_data = {
                            "id": len(paragraphs),
                            "start": paragraph_start,
                            "end": next_chapter_start_time,
                            "speaker": segment_speaker,
                        }

                        if chapter_title is not None:
                            paragraph_data["chapter"] = chapter_title

                        # Create a paragraph for the portion before the chapter
                        paragraphs.append(
                            DigitalPaperEditParagraph(**paragraph_data)
                        )

                    # Update for the new chapter
                    paragraph_start = next_chapter_start_time
                    chapter_title = next_chapter_title

                    # Move to the next chapter
                    chapter_index += 1
                    if chapter_index < len(chapters):
                        (
                            _,
                            next_chapter_start_time,
                            next_chapter_title,
                        ) = chapters[chapter_index]
                    else:
                        next_chapter_title = None
                        next_chapter_start_time = float("inf")

                for word in sentence["words"]:
                    digital_paper_edit_word = DigitalPaperEditWord(
                        id=word_id,
                        start=word["start"],
                        end=word["end"],
                        text=word["punctuated_word"],
                    )
                    words.append(digital_paper_edit_word)
                    word_id += 1

                current_sentence_index += 1

            # Add remaining part of the segment as a paragraph
            paragraphs.append(
                DigitalPaperEditParagraph(
                    id=len(paragraphs),
                    start=paragraph_start,
                    end=segment_end,
                    speaker=segment_speaker,
                    chapter=chapter_title
                    if paragraph_start < next_chapter_start_time
                    else None,
                )
            )

        return DigitalPaperEditFormat(words=words, paragraphs=paragraphs)

    def construct_transcript(
        self, speaker_segments: list[SpeakerSegmentWithSentences], chapters
    ):
        def add_timestamp(speaker, timestamp):
            return f"Speaker {speaker}: {utils.decimal_to_sexagesimal(timestamp)}\n\n"

        def construct_sentence(sentence: Sentence):
            """
            Constructs a sentence string from individual words.
            """

            def construct_sentence_with_confidence_annotations(
                sentence: Sentence,
            ):
                """
                Constructs a sentence string with embedded speaker confidence annotations.
                This method constructs a sentence string from individual words, appending the speaker confidence
                for each word or group of words with the same confidence. In development mode, this aids in
                analyzing and debugging the sentence construction process by providing clear visibility of
                confidence levels and sentence modification points.
                """
                final_sentence = ""
                num_words = len(sentence["words"])
                if num_words == 0:
                    return final_sentence

                current_confidence = round(
                    sentence["words"][0]["speaker_confidence"], 3
                )
                for i, word in enumerate(sentence["words"]):
                    next_confidence = (
                        round(sentence["words"][i + 1]["speaker_confidence"], 3)
                        if i + 1 < num_words
                        else None
                    )

                    final_sentence += word["punctuated_word"]

                    if (
                        next_confidence != current_confidence
                        or i == num_words - 1
                    ):
                        # Append the speaker confidence at the end of a word group with the same confidence
                        final_sentence += f"[{current_confidence}]"
                        if i < num_words - 1:
                            final_sentence += (
                                " "  # Add space if not the final word
                            )
                        current_confidence = next_confidence
                    else:
                        final_sentence += " "

                return final_sentence

            include_annotations = False
            if include_annotations:
                return construct_sentence_with_confidence_annotations(sentence)
            else:
                return " ".join(
                    word["punctuated_word"] for word in sentence["words"]
                )

        try:
            final_transcript = ""
            chapter_index = 0 if chapters else None

            for speaker_data in speaker_segments:
                speaker_id = speaker_data["speaker"]
                single_speaker = speaker_id == "single_speaker"

                for i, sentence_data in enumerate(speaker_data["sentences"]):
                    sentence_start = sentence_data["start"]
                    first_sentence = i == 0
                    last_sentence = i == len(speaker_data["sentences"]) - 1
                    chapter_splits_segment = False

                    if chapter_index is not None and chapter_index < len(
                        chapters
                    ):
                        chapter_id, chapter_start_time, chapter_title = (
                            chapters[chapter_index]
                        )

                        if chapter_start_time <= sentence_start:
                            # Chapter starts at this sentence
                            # Add Chapter title
                            if not first_sentence:
                                final_transcript += "\n"
                                if not self.one_sentence_per_line:
                                    final_transcript += "\n"
                            final_transcript += f"## {chapter_title}\n\n"
                            # Add speaker timestamp for the rest of the speaker's
                            # segment that comes after the chapter title
                            if not single_speaker and not first_sentence:
                                final_transcript += add_timestamp(
                                    speaker_id, chapter_start_time
                                )
                                chapter_splits_segment = True
                            chapter_index += 1

                    if not single_speaker and first_sentence:
                        final_transcript += add_timestamp(
                            speaker_id, sentence_start
                        )

                    # Add the band-aid word if in dev mode
                    if self.dev_mode:
                        final_transcript += (
                            f"{construct_sentence(sentence_data)}\n"
                        )
                    else:
                        if self.one_sentence_per_line:
                            final_transcript += (
                                f"{sentence_data['transcript']}\n"
                            )
                        else:
                            final_transcript += f"{' ' if not first_sentence and not chapter_splits_segment else ''}{sentence_data['transcript']}"
                            final_transcript += "\n" if last_sentence else ""

                final_transcript += "\n"

            return final_transcript.strip()
        except Exception as e:
            raise Exception(f"Error creating output format: {e}")

    def finalize_transcript(self, transcript: Transcript) -> None:
        try:
            if not transcript.outputs["transcription_service_output_file"]:
                raise Exception("No 'deepgram_output' found in JSON")
            with open(
                transcript.outputs["transcription_service_output_file"],
                encoding="utf-8",
            ) as outfile:
                transcription_service_output = json.load(outfile)

            has_diarization = any(
                "speaker" in word
                for word in transcription_service_output["results"]["channels"][
                    0
                ]["alternatives"][0]["words"]
            )

            logger.info(
                f"(deepgram) Finalizing transcript [diarization={has_diarization}, chapters={len(transcript.source.chapters) > 0}]..."
            )
            speaker_segments = self.process_segments(
                transcription_service_output, has_diarization
            )
            speaker_segements_with_sentences = (
                self.break_segments_into_sentences(speaker_segments)
            )
            speaker_segements_with_sentences = self.fix_broken_sentences(
                speaker_segements_with_sentences
            )
            adjusted_chapters = self.adjust_chapter_timestamps(
                speaker_segements_with_sentences, transcript.source.chapters
            )
            if self.dpe_output:
                dpe_format = self.transform_to_digital_paper_edit_format(
                    speaker_segements_with_sentences, adjusted_chapters
                )
                transcript.outputs["dpe_file"] = self.data_writer.write_json(
                    data=dpe_format,
                    file_path=transcript.output_path_with_title,
                    filename="dpe",
                    include_timestamp=False,
                )

            transcript.outputs["raw"] = self.construct_transcript(
                speaker_segements_with_sentences, adjusted_chapters
            )
        except Exception as e:
            raise Exception(f"(deepgram) Error finalizing transcript: {e}")

    def combine_chunk_outputs(self, all_chunks_output, overlap):
        combined_output = {
            "results": {"channels": [{"alternatives": [{"words": []}]}]},
            "metadata": [],  # Initialize metadata as an empty array
        }

        # Add summaries field if self.summarize is True
        if self.summarize:
            combined_output["results"]["channels"][0]["alternatives"][0][
                "summaries"
            ] = []

        global_speaker_mapping = {}
        global_speaker_counter = 0
        previous_words = []
        total_offset = 0

        for chunk_index, chunk_output in enumerate(all_chunks_output):
            words = chunk_output["results"]["channels"][0]["alternatives"][0][
                "words"
            ]
            metadata = chunk_output.get("metadata", {})

            # Adjust word timestamps based on the total offset
            for word in words:
                word["start"] += total_offset
                word["end"] += total_offset

            # Calculate chunk_end based on the last word's end time
            words[-1]["end"] if words else 0

            # Create a local to global speaker mapping for the current chunk
            local_to_global_speaker_mapping = {}

            # Use overlap to match speakers between chunks
            if previous_words:
                for prev_word in previous_words:
                    for curr_word in words:
                        if (
                            abs(prev_word["start"] - curr_word["start"])
                            < overlap
                        ):
                            local_speaker = curr_word["speaker"]
                            if (
                                local_speaker
                                not in local_to_global_speaker_mapping
                            ):
                                if local_speaker not in global_speaker_mapping:
                                    global_speaker_mapping[local_speaker] = (
                                        global_speaker_counter
                                    )
                                    global_speaker_counter += 1
                                local_to_global_speaker_mapping[
                                    local_speaker
                                ] = global_speaker_mapping[local_speaker]
                            curr_word["speaker"] = (
                                local_to_global_speaker_mapping[local_speaker]
                            )

            for word in words:
                local_speaker = word["speaker"]
                if local_speaker not in local_to_global_speaker_mapping:
                    if local_speaker not in global_speaker_mapping:
                        global_speaker_mapping[local_speaker] = (
                            global_speaker_counter
                        )
                        global_speaker_counter += 1
                    local_to_global_speaker_mapping[local_speaker] = (
                        global_speaker_mapping[local_speaker]
                    )

                global_speaker = local_to_global_speaker_mapping[local_speaker]
                word["speaker"] = global_speaker

            # Remove overlapping words from the current chunk's words list
            non_overlap_words = [
                word
                for word in words
                if word["end"]
                >= (total_offset + overlap if chunk_index != 0 else 0)
            ]
            combined_output["results"]["channels"][0]["alternatives"][0][
                "words"
            ].extend(non_overlap_words)

            # Append the metadata of the current chunk
            combined_output["metadata"].append(metadata)

            if self.summarize:
                summaries = chunk_output["results"]["channels"][0][
                    "alternatives"
                ][0].get("summaries", [])
                combined_output["results"]["channels"][0]["alternatives"][0][
                    "summaries"
                ].extend(summaries)

            # Update the total offset for the next chunk
            total_offset += self.processor.chunk_length - overlap

            # Update previous_words to the last words of the current chunk within the overlap duration
            previous_words = [
                word for word in words if word["end"] > total_offset
            ]

        return combined_output

    def transcribe_in_chunks(self, transcript: Transcript):
        # Split audio into chunks
        overlap_between_chunks = 30.0
        chunk_files = self.processor.split_audio(
            transcript.audio_file, overlap=overlap_between_chunks
        )
        # TODO print information about the chunking
        all_chunks_output = []
        deepgram_chunks = []
        for i, chunk_file in enumerate(chunk_files):
            chunk_output = self.audio_to_text(chunk_file, i + 1)
            all_chunks_output.append(chunk_output)

            # Write intermediate deepgram output to JSON file
            filename = f"deepgram_chunk_{i + 1}_of_{len(chunk_files)}"
            result = self.data_writer.write_json(
                data=chunk_output,
                file_path=transcript.output_path_with_title,
                filename=filename,
            )
            deepgram_chunks.append(os.path.basename(result))

        # Combine all chunk outputs into a single output
        transcription_service_output = self.combine_chunk_outputs(
            all_chunks_output, overlap=overlap_between_chunks
        )

        # Update transcript's metadata file with chunk filenames
        if transcript.metadata_file is not None:
            with open(transcript.metadata_file) as file:
                data = json.load(file)
            data["deepgram_chunks"] = deepgram_chunks
            with open(transcript.metadata_file, "w") as file:
                json.dump(data, file, indent=4)

        return transcription_service_output

    def transcribe(self, transcript: Transcript) -> None:
        try:
            audio_duration = librosa.get_duration(path=transcript.audio_file)
            transcription_service_output = {}

            if audio_duration > self.max_audio_length:
                logger.info(
                    f"Audio file is longer than {self.max_audio_length / 60} minutes. Splitting into {self.processor.chunk_length / 60} min chunks."
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
            if self.upload:
                application.upload_file_to_s3(
                    transcript.outputs["transcription_service_output_file"]
                )
            if self.summarize:
                transcript.summary = self.process_summary(transcript)
            self.finalize_transcript(transcript)
        except Exception as e:
            raise Exception(f"(deepgram) Error while transcribing: {e}")
