import logging
from typing import TYPE_CHECKING

from dotenv import load_dotenv

load_dotenv()

if TYPE_CHECKING:
    from backend.util.process import AppProcess

logger = logging.getLogger(__name__)


def run_processes(*processes: "AppProcess", **kwargs):
    """
    Execute all processes in the app. The last process is run in the foreground.
    Includes enhanced error handling and process lifecycle management.
    """
    try:
        # Run all processes except the last one in the background.
        for process in processes[:-1]:
            process.start(background=True, **kwargs)

        # Run the last process in the foreground.
        processes[-1].start(background=False, **kwargs)
    finally:
        for process in reversed(processes):
            try:
                process.stop()
            except Exception as e:
                logger.exception(f"[{process.service_name}] unable to stop: {e}")


def main(**kwargs):
    """
    Run all the processes required for the AutoGPT-server (REST and WebSocket APIs).
    """
    import os

    from backend.api.rest_api import AgentServer
    from backend.api.ws_api import WebsocketServer
    from backend.copilot.executor.manager import CoPilotExecutor
    from backend.data.db_manager import DatabaseManager
    from backend.executor import ExecutionManager, Scheduler
    from backend.notifications import NotificationManager

    processes = [
        DatabaseManager().set_log_level("warning"),
        Scheduler(),
        NotificationManager(),
        WebsocketServer(),
        AgentServer(),
        ExecutionManager(),
        CoPilotExecutor(),
    ]

    if os.getenv("AUTOPILOT_BOT_DISCORD_TOKEN"):
        from backend.copilot.bot.app import CoPilotBot

        processes.append(CoPilotBot())
        logger.info("CoPilotBot enabled (AUTOPILOT_BOT_DISCORD_TOKEN set)")

    run_processes(*processes, **kwargs)


if __name__ == "__main__":
    main()
