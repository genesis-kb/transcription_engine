import functools

import requests

from app.logging import get_logger


logger = get_logger()


def api_error_handler(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            response = func(*args, **kwargs)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"API request failed: {e}")
            if e.response is not None:
                try:
                    error_detail = e.response.json().get(
                        "detail", "No detail provided"
                    )
                    logger.error(f"Error detail: {error_detail}")
                except ValueError:
                    logger.error(
                        f"Error response was not JSON. Content: {e.response.text}"
                    )
            else:
                logger.error("No response received from server")
            raise
        except Exception as e:
            logger.error(f"An unexpected error occurred: {e}")
            raise

    return wrapper


class APIClient:
    """
    A client for interacting with the transcription API.

    This class encapsulates all API calls related to transcription operations.
    It handles the construction of API endpointsand applies error handling
    to all requests.
    """

    def __init__(self, base_url):
        self.base_url = base_url

    @api_error_handler
    def add_to_queue(self, data, source):
        if source.endswith(".json"):
            with open(source, "rb") as f:
                files = {"source_file": (source, f, "application/json")}
                return requests.post(
                    f"{self.base_url}/transcription/add_to_queue/",
                    data=data,
                    files=files,
                )
        else:
            data["source"] = source
            return requests.post(
                f"{self.base_url}/transcription/add_to_queue/", data=data
            )

    @api_error_handler
    def start_transcription(self):
        return requests.post(f"{self.base_url}/transcription/start/")

    @api_error_handler
    def preprocess_source(self, data, source):
        if source.endswith(".json"):
            with open(source, "rb") as f:
                files = {"source_file": (source, f, "application/json")}
                return requests.post(
                    f"{self.base_url}/transcription/preprocess/",
                    data=data,
                    files=files,
                )
        else:
            data["source"] = source
            return requests.post(
                f"{self.base_url}/transcription/preprocess/", data=data
            )

    @api_error_handler
    def get_queue(self):
        return requests.get(f"{self.base_url}/transcription/queue/")

    @api_error_handler
    def add_translation_to_queue(self, data, source):
        with open(source, "rb") as f:
            files = {"source_file": (source, f, "text/plain")}
            return requests.post(
                f"{self.base_url}/translation/add_to_queue/",
                data=data,
                files=files,
            )

    @api_error_handler
    def start_translation(self):
        return requests.post(f"{self.base_url}/translation/start/")

