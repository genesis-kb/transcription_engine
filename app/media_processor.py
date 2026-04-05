import os

import ffmpeg
import librosa
import requests
import soundfile as sf
import yt_dlp

from app import logging, utils
from app.config import settings


def _yt_opts(**extra):
    """Build yt-dlp options with cookies if available."""
    opts = {**extra}
    if settings.YT_COOKIES_FILE and os.path.exists(settings.YT_COOKIES_FILE):
        opts["cookiefile"] = settings.YT_COOKIES_FILE
    return opts


logger = logging.get_logger()


class MediaProcessor:
    def __init__(self, chunk_length=1200.0):
        self.chunk_length = chunk_length
        self.invidious_instances = [
            "https://invidious.fdn.fr",
            "https://inv.tux.pizza",
            "https://invidious.flokinet.to",
        ]

    def initialize_ffmpeg(self):
        # Check if ffmpeg is available
        try:
            ffmpeg.probe("")
            logger.debug("FFMPEG is already available in the system PATH.")
        except ffmpeg.Error:
            try:
                logger.debug("Initializing FFMPEG...")
                import static_ffmpeg

                static_ffmpeg.add_paths()
                logger.debug("Initialized FFMPEG")
            except ImportError:
                logger.debug(
                    "static_ffmpeg not found, assuming ffmpeg is available system-wide"
                )
            except Exception as e:
                logger.error(f"Error initializing FFMPEG: {e}")
                raise Exception("Error initializing FFMPEG")

    def split_audio(self, audio_path, output_dir=None, overlap=0):
        # Set default output directory if not provided
        if output_dir is None:
            output_dir = os.path.splitext(audio_path)[0] + "_chunks"

        # Load the audio file
        audio, sr = librosa.load(audio_path, sr=None)
        duration = librosa.get_duration(y=audio, sr=sr)

        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        # Array to store paths of chunks
        chunk_paths = []

        # Split the audio into chunks
        chunk_start = 0
        chunk_counter = 1

        while chunk_start < duration:
            chunk_end = min(chunk_start + self.chunk_length, duration)
            chunk_audio = audio[int(chunk_start * sr) : int(chunk_end * sr)]
            chunk_path = os.path.join(output_dir, f"chunk_{chunk_counter}.mp3")
            sf.write(chunk_path, chunk_audio, sr)
            logger.debug(
                f"Saved chunk {chunk_counter} to {chunk_path} (start={chunk_start:.2f}s, end={chunk_end:.2f}s, duration={chunk_end - chunk_start:.2f}s)"
            )
            chunk_paths.append(chunk_path)
            chunk_counter += 1

            if chunk_end == duration:
                break

            chunk_start = (
                chunk_end - overlap
            )  # Move start point back by overlap duration

        return chunk_paths

    def convert_to_mp3(self, input_path, output_path=None):
        if output_path is None:
            output_path = os.path.splitext(input_path)[0] + ".mp3"
        else:
            filename = os.path.splitext(os.path.basename(input_path))[0]
            output_path = os.path.abspath(
                os.path.join(output_path, f"{utils.slugify(filename)}.mp3")
            )

        logger.debug(f"Converting {input_path} to {output_path}")
        self.initialize_ffmpeg()
        try:
            ffmpeg.input(input_path).output(output_path, format="mp3").run()
            logger.debug(
                f"Successfully converted {input_path} to {output_path}"
            )
            return output_path
        except ffmpeg.Error as e:
            logger.error(f"Error converting {input_path} to mp3: {e}")
            raise Exception(f"Error converting {input_path} to mp3: {e}")

    def get_yt_dlp_url(self, youtube_url):
        """
        Extracts and returns the direct URL of a YouTube video using yt_dlp.
        """
        ydl_opts = _yt_opts(format="best", quiet=True, no_warnings=True)

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(youtube_url, download=False)
                video_url = info_dict.get("url", None)
                if video_url and self.check_url(video_url):
                    return video_url
        except Exception as e:
            logger.error(f"Error extracting video URL with yt_dlp: {e}")
        return None

    def get_invidious_url(self, youtube_url):
        """
        Extracts and returns the direct URL of a YouTube video using Invidious.
        Tries multiple Invidious instances until one succeeds.
        """
        video_id = youtube_url.split("v=")[1]

        for instance in self.invidious_instances:
            api_url = f"{instance}/api/v1/videos/{video_id}"
            try:
                response = requests.get(api_url)
                if response.status_code == 200:
                    video_info = response.json()
                    video_url = video_info["formatStreams"][0]["url"]
                    if self.check_url(video_url):
                        return video_url
                else:
                    logger.error(
                        f"Error fetching video info from {instance}: {response.text} ({response.status_code})"
                    )
            except Exception as e:
                logger.error(f"Error fetching video URL from {instance}: {e}")

        return None

    def check_url(self, url):
        """Check if the given URL is accessible."""
        try:
            response = requests.head(url, allow_redirects=True, timeout=5)
            return response.status_code == 200
        except requests.RequestException as e:
            logger.error(f"Error checking URL: {e}")
            return False

    def get_youtube_video_url(self, youtube_url):
        """
        Attempts to get the video URL first using Invidious, and if that fails,
        falls back to using yt_dlp.
        """
        video_url = self.get_invidious_url(youtube_url)
        if not video_url:
            video_url = self.get_yt_dlp_url(youtube_url)
        return video_url

    def get_youtube_video_info(self, youtube_url):
        """Extracts video metadata using yt_dlp."""
        ydl_opts = _yt_opts(quiet=True, no_warnings=True)
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(youtube_url, download=False)
        except Exception as e:
            logger.error(f"Error extracting video info: {e}")
            raise

    def download_youtube_video(
        self,
        youtube_url,
        output_dir=None,
        format_selector="best",
        filename_template="%(title)s.%(ext)s",
    ):
        """
        Downloads a YouTube video using yt_dlp.
        For more information on format selection, see:
        https://github.com/yt-dlp/yt-dlp#format-selection-examples
        """
        if output_dir is None:
            output_dir = os.getcwd()

        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        ydl_opts = _yt_opts(
            format=format_selector,
            outtmpl=os.path.join(output_dir, filename_template),
            nopart=True,
        )

        try:
            logger.debug(f"Downloading video: {youtube_url}")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(youtube_url, download=True)
                filename = ydl.prepare_filename(info_dict)
                logger.info(
                    f"Successfully downloaded {youtube_url} to {filename}"
                )
                return filename
        except Exception as e:
            error_message = (
                f"Error downloading youtube video ({format_selector}): {e}"
            )
            logger.error(error_message)
            raise Exception(error_message)
