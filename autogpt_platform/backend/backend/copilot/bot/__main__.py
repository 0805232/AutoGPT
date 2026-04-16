"""Entry point for running the CoPilot Bot service.

Usage:
    poetry run copilot-bot
    python -m backend.copilot.bot
"""

from backend.app import run_processes

from .app import CoPilotBot


def main():
    """Run the CoPilot Bot service."""
    run_processes(CoPilotBot())


if __name__ == "__main__":
    main()
