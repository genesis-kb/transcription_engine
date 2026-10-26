import logging

import click
import uvicorn

from app.config import settings
from app.logging import configure_logger, get_logger
from server import app


configure_logger(
    logging.DEBUG
    if settings.config.getboolean("verbose_logging", False)
    else logging.INFO
)
logger = get_logger()


@click.command()
@click.argument("mode", type=click.Choice(["dev", "prod"]))
@click.option("--host", default="0.0.0.0", help="The host to bind to")
@click.option("--port", default=8000, help="The port to bind to")
def run(mode, host, port):
    """Run the server in the specified mode."""
    logger.info("Starting transcription server...")
    logger.info(settings.get_config_overview())

    if mode == "dev":
        uvicorn.run("server:app", host=host, port=port, reload=True)
    else:
        uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run()
