import json
import os
import subprocess
import sys
import time
from functools import update_wrapper

import click
import psutil
import requests

from app.config import settings


def get_transcription_url():
    url = settings.TRANSCRIPTION_SERVER_URL
    if not url:
        raise click.ClickException(
            "TRANSCRIPTION_SERVER_URL is not set in the environment or .env file. "
            "Please set it and try again."
        )
    return url


def is_server_running(url):
    try:
        response = requests.get(f"{url}/health", timeout=5)
        return response.status_code == 200
    except requests.RequestException:
        return False


def get_server_pid_file(mode):
    """Get the path to the server PID file."""
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    pid_dir = os.path.join(base_dir, "logs")
    os.makedirs(pid_dir, exist_ok=True)
    return os.path.join(pid_dir, f"server_{mode}.pid")


def is_process_running(pid):
    """Check if a process with the given PID is running."""
    try:
        process = psutil.Process(pid)
        return process.is_running()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return False


def get_running_server_info(mode):
    """Get information about a running server process."""
    pid_file = get_server_pid_file(mode)
    if not os.path.exists(pid_file):
        return None

    try:
        with open(pid_file) as f:
            data = json.load(f)

        pid = data.get("pid")
        if pid and is_process_running(pid):
            return data

        # PID file exists but process is not running, clean up
        os.remove(pid_file)
    except (OSError, json.JSONDecodeError):
        # Invalid PID file, clean up
        os.remove(pid_file)

    return None


def start_server(host="0.0.0.0", port=8000, mode="prod", verbose=False):
    """Start the transcription server as a subprocess.

    Args:
        host: The host to bind to
        port: The port to bind to
        mode: The server mode ('dev' or 'prod')
        verbose: Whether to show server output directly in the console
    """
    # Check if server is already running
    server_info = get_running_server_info(mode)
    if server_info:
        click.echo(
            f"Transcription server is already running (PID: {server_info['pid']})."
        )
        return True

    # Get the path to the transcriber_server.py script
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    server_script = os.path.join(base_dir, "transcriber_server.py")

    # Create logs directory if it doesn't exist
    logs_dir = os.path.join(base_dir, "logs")
    os.makedirs(logs_dir, exist_ok=True)

    # Log file paths
    log_file = os.path.join(logs_dir, f"server_{mode}.log")
    pid_file = get_server_pid_file(mode)

    click.echo(
        "Transcription server is not running. Starting it automatically..."
    )

    if verbose:
        # In verbose mode, show server output directly in the console
        click.echo(
            "Starting server in verbose mode. Server will continue running in the background."
        )
        process = subprocess.Popen(
            [
                sys.executable,
                server_script,
                mode,
                "--host",
                host,
                "--port",
                str(port),
            ]
        )
    else:
        # In normal mode, redirect server output to a log file
        click.echo(f"Server logs will be written to: {log_file}")

        # Open log file
        with open(log_file, "a") as f:
            # Write a separator for new log session
            f.write("\n\n" + "=" * 50 + "\n")
            f.write(f"Server started at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 50 + "\n\n")

            # Use Python executable to run the server script
            process = subprocess.Popen(
                [
                    sys.executable,
                    server_script,
                    mode,
                    "--host",
                    host,
                    "--port",
                    str(port),
                ],
                stdout=f,
                stderr=f,
                text=True,
            )

    # Save the PID to a file
    server_info = {
        "pid": process.pid,
        "mode": mode,
        "host": host,
        "port": port,
        "start_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "log_file": log_file,
    }

    with open(pid_file, "w") as f:
        json.dump(server_info, f)

    # Wait for the server to start
    url = get_transcription_url()
    max_retries = 10
    retry_interval = 1

    for _ in range(max_retries):
        if is_server_running(url):
            click.echo("Transcription server started successfully.")
            click.echo(
                f"Server is running with PID {process.pid}. Use 'tstbtc server stop' to stop it."
            )
            return True
        time.sleep(retry_interval)

    click.echo("Failed to start transcription server.", err=True)

    # Clean up if server failed to start
    try:
        process.terminate()
        os.remove(pid_file)
    except OSError:
        pass

    return False


def stop_server(mode="prod"):
    """Stop the transcription server."""
    server_info = get_running_server_info(mode)
    if not server_info:
        click.echo(f"No {mode} server is currently running.")
        return False

    pid = server_info["pid"]
    click.echo(f"Stopping transcription server (PID: {pid})...")

    try:
        process = psutil.Process(pid)
        process.terminate()

        # Wait for the process to terminate
        try:
            process.wait(timeout=5)
        except psutil.TimeoutExpired:
            click.echo("Server did not terminate gracefully, forcing...")
            process.kill()

        # Remove the PID file
        os.remove(get_server_pid_file(mode))
        click.echo("Transcription server stopped.")
        return True
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        # Process already gone, just remove the PID file
        os.remove(get_server_pid_file(mode))
        click.echo(
            "Transcription server was not running (stale PID file removed)."
        )
        return True
    except Exception as e:
        click.echo(f"Error stopping server: {e}", err=True)
        return False


def auto_start_server(f=None):
    """
    Decorator for commands that should auto-start the server.
    This wraps the command's callback to check if the server is running and potentially start it before executing.
    """

    def decorator(f):
        @click.pass_context
        def new_callback(ctx, *args, **kwargs):
            # Skip server check if showing help
            if any(
                help_opt in ctx.protected_args
                for help_opt in ctx.help_option_names
            ):
                return ctx.invoke(f, *args, **kwargs)

            try:
                url = get_transcription_url()
                if not is_server_running(url):
                    # Check if auto_server is enabled from context
                    auto_server = (
                        ctx.obj.get("auto_server", True) if ctx.obj else True
                    )
                    server_mode = (
                        ctx.obj.get("server_mode", "prod")
                        if ctx.obj
                        else "prod"
                    )
                    server_verbose = (
                        ctx.obj.get("server_verbose", False)
                        if ctx.obj
                        else False
                    )

                    if auto_server:
                        # Try to start the server
                        click.echo(
                            f"Auto-starting server for command: {ctx.command.name}"
                        )
                        if not start_server(
                            mode=server_mode, verbose=server_verbose
                        ):
                            raise click.ClickException(
                                "Could not start the transcription server. "
                                "Please start it manually and try again."
                            )
                    else:
                        # Auto-server is disabled, show the original error
                        raise click.ClickException(
                            "Transcription server is not running. "
                            "Please start the server with 'tstbtc server start' "
                            "or re-run without --no-auto-server."
                        )
            except click.ClickException as e:
                click.echo(str(e), err=True)
                ctx.exit(1)

            # Server is running or has been started, proceed with the command
            return ctx.invoke(f, *args, **kwargs)

        return update_wrapper(new_callback, f)

    # Handle both @auto_start_server and @auto_start_server() syntax
    if f is None:
        return decorator
    return decorator(f)
