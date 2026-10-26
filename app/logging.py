import logging
import sys
from pathlib import Path

from app import __app_name__


def use_utf8_output():
    """Write stdout/stderr as UTF-8.

    When output is redirected (to a file, a pipe, or the server log), Python
    on Windows falls back to the locale encoding (e.g. cp1252), which cannot
    encode characters such as "→" used in help text and log messages.
    """
    for stream in (sys.stdout, sys.stderr):
        encoding = (getattr(stream, "encoding", None) or "").lower()
        if hasattr(stream, "reconfigure") and encoding != "utf-8":
            stream.reconfigure(encoding="utf-8")


def configure_logger(log_level, working_dir=None):
    logger = get_logger()
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)
    sh = logging.StreamHandler()
    sh_log_fmt = "%(asctime)s [%(levelname)s] %(message)s"
    sh.setLevel(log_level)
    sh.setFormatter(logging.Formatter(sh_log_fmt))

    # Always log debug out to a file in the workdir
    if working_dir is not None:
        filehandler = logging.FileHandler(
            Path(working_dir) / "tstbtc.log", encoding="utf-8"
        )
        filehandler.setLevel(logging.DEBUG)
        file_log_fmt = "%(asctime)s %(name)s [%(levelname)s] %(message)s"
        filehandler.setFormatter(logging.Formatter(file_log_fmt))
        logger.addHandler(filehandler)

    logger.addHandler(sh)
    logger.setLevel(logging.DEBUG)


def get_logger():
    return logging.getLogger(__app_name__)
