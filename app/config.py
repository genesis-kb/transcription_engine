import base64
import configparser
import os
import urllib.parse

from dotenv import load_dotenv

from app.exceptions import MissingEnvironmentVariableError


def read_config(profile):
    config = configparser.ConfigParser()
    config.read("config.ini")
    return config[profile]


class Settings:
    def __init__(self):
        # Reload environment variables from .env file
        load_dotenv(override=True)

        # server
        self.TSTBTC_METADATA_DIR = os.getenv("TSTBTC_METADATA_DIR")
        # yt-dlp cookies file for YouTube authentication
        self.YT_COOKIES_FILE = os.getenv("YT_COOKIES_FILE", "cookies.txt")
        # Global proxy settings
        self.USE_PROXY = str(os.getenv("USE_PROXY", "false")).lower() == "true"
        self.PROXY_URL = os.getenv("PROXY_URL", "")
            
        # GitHub API settings
        self.GITHUB_REPO_OWNER = os.getenv(
            "GITHUB_REPO_OWNER", "bitcointranscripts"
        )
        self.GITHUB_REPO_NAME = os.getenv(
            "GITHUB_REPO_NAME", "bitcointranscripts"
        )
        self.GITHUB_METADATA_REPO_NAME = os.getenv(
            "GITHUB_METADATA_REPO_NAME", "bitcointranscripts-metadata"
        )

        # cli
        self.TRANSCRIPTION_SERVER_URL = os.getenv("TRANSCRIPTION_SERVER_URL")

        # Load configuration from config.ini
        self.PROFILE = os.getenv("PROFILE", "DEFAULT")
        self.config = read_config(self.PROFILE)

        if self.USE_PROXY and self.PROXY_URL:
            os.environ["http_proxy"] = self.PROXY_URL
            os.environ["https_proxy"] = self.PROXY_URL
            os.environ["HTTP_PROXY"] = self.PROXY_URL
            os.environ["HTTPS_PROXY"] = self.PROXY_URL
            
            # Prevent local traffic from being proxied
            no_proxy_list = ["localhost", "127.0.0.1", "::1", "server"]
            if self.TRANSCRIPTION_SERVER_URL:
                try:
                    parsed_url = urllib.parse.urlparse(self.TRANSCRIPTION_SERVER_URL)
                    if parsed_url.hostname and parsed_url.hostname not in no_proxy_list:
                        no_proxy_list.append(parsed_url.hostname)
                except Exception:
                    pass
            # Merge inherited NO_PROXY entries with the new local-service exclusions
            existing_no_proxy = os.getenv("NO_PROXY", "") or os.getenv("no_proxy", "")
            existing_entries = [e.strip() for e in existing_no_proxy.split(",") if e.strip()]
            for entry in existing_entries:
                if entry not in no_proxy_list:
                    no_proxy_list.append(entry)
            merged_no_proxy = ",".join(no_proxy_list)
            os.environ["no_proxy"] = merged_no_proxy
            os.environ["NO_PROXY"] = merged_no_proxy

    def get_config_overview(self):
        overview = "Configuration Settings:\n"
        overview += f"PROFILE: {self.PROFILE}\n"
        overview += f"TSTBTC_METADATA_DIR: {self.TSTBTC_METADATA_DIR}\n"
        overview += f"GITHUB_REPO_OWNER: {self.GITHUB_REPO_OWNER}\n"
        overview += f"GITHUB_REPO_NAME: {self.GITHUB_REPO_NAME}\n"
        overview += (
            f"GITHUB_METADATA_REPO_NAME: {self.GITHUB_METADATA_REPO_NAME}\n"
        )
        overview += (
            f"TRANSCRIPTION_SERVER_URL: {self.TRANSCRIPTION_SERVER_URL}\n"
        )
        overview += f"BTC_TRANSCRIPTS_URL: {self.BTC_TRANSCRIPTS_URL}\n"

        # Add config.ini settings
        overview += "\nSettings from config.ini:\n"
        for key, value in self.config.items():
            overview += f"{key}: {value}\n"

        return overview

    @staticmethod
    def _get_env_variable(var_name, custom_message=None):
        value = os.getenv(var_name)
        if not value:
            raise MissingEnvironmentVariableError(var_name, custom_message)
        return value

    @property
    def DEEPGRAM_API_KEY(self):
        return self._get_env_variable(
            "DEEPGRAM_API_KEY",
            "To use Deepgram as a transcription service you need to define a 'DEEPGRAM_API_KEY' in your .env file",
        )

    @property
    def BTC_TRANSCRIPTS_URL(self):
        return self._get_env_variable("BTC_TRANSCRIPTS_URL")

    @property
    def S3_BUCKET(self):
        return self._get_env_variable("S3_BUCKET")

    @property
    def GITHUB_APP_ID(self):
        return self._get_env_variable(
            "GITHUB_APP_ID",
            "To use GitHub App integration, you need to define a 'GITHUB_APP_ID' in your .env file",
        )

    @property
    def GITHUB_PRIVATE_KEY(self):
        return base64.b64decode(
            self._get_env_variable(
                "GITHUB_PRIVATE_KEY_BASE64",
                "To use GitHub App integration, you need to define a 'GITHUB_PRIVATE_KEY' in your .env file",
            )
        ).decode("utf-8")

    @property
    def GITHUB_INSTALLATION_ID(self):
        return self._get_env_variable(
            "GITHUB_INSTALLATION_ID",
            "To use GitHub App integration, you need to define a 'GITHUB_INSTALLATION_ID' in your .env file",
        )

    @property
    def LLM_PROVIDER(self):
        return self.config.get("llm_provider", "openai")

    @property
    def OPENAI_API_KEY(self):
        return self._get_env_variable("OPENAI_API_KEY")

    @property
    def SMALLEST_API_KEY(self):
        return self._get_env_variable(
            "SMALLEST_API_KEY",
            "To use SmallestAI Pulse STT you need to define a 'SMALLEST_API_KEY' in your .env file",
        )

    @property
    def YOUTUBE_API_KEY(self):
        return self._get_env_variable(
            "YOUTUBE_API_KEY",
            "To use YouTube channel scanning you need to define a 'YOUTUBE_API_KEY' in your .env file",
        )

    @property
    def GOOGLE_API_KEY(self):
        return self._get_env_variable("GOOGLE_API_KEY")

    @property
    def CLAUDE_API_KEY(self):
        return self._get_env_variable("CLAUDE_API_KEY")

    @property
    def HF_TOKEN(self):
        return self._get_env_variable(
            "HF_TOKEN",
            "To use VibeVoice you need to define an 'HF_TOKEN' in your .env file",
        )

    @property
    def DATABASE_URL(self):
        return os.getenv("DATABASE_URL")

    @property
    def ASR_PROVIDER(self):
        return self.config.get("asr_provider", "whisper")

    @property
    def SARVAM_API_KEY(self):
        return self._get_env_variable(
            "SARVAM_API_KEY",
            "To use Sarvam AI translation you need a 'SARVAM_API_KEY' in your .env file",
        )

    @property
    def GENESIS_KB_REGISTRY_PATH(self):
        return os.getenv("GENESIS_KB_REGISTRY_PATH", "genesis_kb_registry.json")

    @property
    def GEMMA_MODEL(self):
        return os.getenv("GEMMA_MODEL", "gemma3:4b")


# Initialize the Settings class and expose an instance
settings = Settings()

__all__ = ["settings"]
