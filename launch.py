"""Starts the app. Double-click the launcher for your system instead of running this directly.

First run: creates a private Python environment in this folder and installs the
libraries (a few minutes). Every run: starts the app and opens it in your browser.
"""

import shutil
import socket
import subprocess
import sys
import time
import venv
import webbrowser
from pathlib import Path

FOLDER = Path(__file__).resolve().parent
ENVIRONMENT = FOLDER / ".venv"
INSTALLED_MARKER = ENVIRONMENT / "installed.txt"


def environment_python() -> Path:
    if sys.platform == "win32":
        return ENVIRONMENT / "Scripts" / "python.exe"
    return ENVIRONMENT / "bin" / "python"


def update_from_github() -> None:
    """Fetch the newest version of the app before starting, if there is one.

    Only ever moves forward to what is on GitHub. If that can't be done
    cleanly (no internet, or files changed here that also changed there) it
    leaves everything as it is and starts the version already on this computer.
    """
    if not (FOLDER / ".git").exists() or shutil.which("git") is None:
        return
    try:
        result = subprocess.run(["git", "pull", "--ff-only", "--quiet"], cwd=FOLDER,
                                capture_output=True, text=True, timeout=60)
    except (subprocess.TimeoutExpired, OSError):
        return
    if result.returncode != 0:
        print("Couldn't fetch the newest version automatically, so starting the one already "
              "here. To update, ask Claude Code to \"pull the latest version\".", flush=True)


def install_if_needed() -> None:
    """Set up the environment once, and again only if requirements.txt changes."""
    requirements = (FOLDER / "requirements.txt").read_text()
    if INSTALLED_MARKER.exists() and INSTALLED_MARKER.read_text() == requirements:
        return
    print("Setting up for the first time. This takes a few minutes…", flush=True)
    if not environment_python().exists():
        venv.create(ENVIRONMENT, with_pip=True)
    subprocess.run(
        [str(environment_python()), "-m", "pip", "install", "--quiet", "-r",
         str(FOLDER / "requirements.txt")],
        check=True,
    )
    INSTALLED_MARKER.write_text(requirements)


def free_port() -> int:
    """Ask the system for a port nothing else is using."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def is_listening(port: int) -> bool:
    with socket.socket() as probe:
        probe.settimeout(0.5)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def main() -> int:
    update_from_github()
    install_if_needed()
    port = free_port()
    app = subprocess.Popen(
        [str(environment_python()), "-m", "streamlit", "run", str(FOLDER / "app.py"),
         "--server.port", str(port), "--server.address", "127.0.0.1",
         "--server.headless", "true", "--browser.gatherUsageStats", "false"],
        cwd=FOLDER,
    )
    # Wait for the app to come up, then open it.
    for _ in range(120):
        if app.poll() is not None:
            print("The app stopped while starting. See the messages above.")
            return 1
        if is_listening(port):
            break
        time.sleep(0.5)
    address = f"http://localhost:{port}"
    print(f"\nEquity Research is running at {address}")
    print("Keep this window open while you use it. Close it to stop the app.\n", flush=True)
    webbrowser.open(address)
    try:
        return app.wait()
    except KeyboardInterrupt:
        app.terminate()
        return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:  # noqa: BLE001 - show the problem instead of vanishing
        print(f"\nCouldn't start: {error}")
        sys.exit(1)
