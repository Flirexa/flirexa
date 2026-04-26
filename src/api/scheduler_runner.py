"""
Standalone scheduler entrypoint.

Keeps the existing in-process scheduler behavior intact, while allowing future
deployments to run monitoring/backup loops outside the API process.
"""

import asyncio
import os
import signal

from loguru import logger

from ..database.connection import close_db, init_db
from .scheduler import start_background_tasks, stop_background_tasks


def validate_scheduler_standalone_mode() -> tuple[bool, str]:
    """
    Hard safety guard against duplicate background execution.

    The project already has two supported modes:
    1. in-process scheduler inside the API
    2. external worker_main.py with WORKER_ENABLED=true

    A standalone scheduler runner is only safe as an explicit third mode.
    """
    if os.getenv("WORKER_ENABLED", "false").lower() == "true":
        return False, "Refusing to start scheduler_runner: WORKER_ENABLED=true already enables external background work"
    if os.getenv("SCHEDULER_IN_API", "true").lower() == "true":
        return False, "Refusing to start scheduler_runner: SCHEDULER_IN_API=true would duplicate API background tasks"
    if os.getenv("SCHEDULER_STANDALONE_ENABLED", "false").lower() != "true":
        return False, "Refusing to start scheduler_runner: set SCHEDULER_STANDALONE_ENABLED=true explicitly"
    return True, "Standalone scheduler mode validated"


async def _run() -> None:
    ok, reason = validate_scheduler_standalone_mode()
    if not ok:
        raise RuntimeError(reason)

    init_db()
    logger.info("Standalone scheduler runner starting")
    tasks = start_background_tasks()
    stop_event = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass

    try:
        await stop_event.wait()
    finally:
        logger.info("Standalone scheduler runner stopping")
        await stop_background_tasks(tasks)
        close_db()


def main() -> None:
    ok, reason = validate_scheduler_standalone_mode()
    if not ok:
        logger.error(reason)
        raise SystemExit(2)
    logger.info(reason)
    asyncio.run(_run())


if __name__ == "__main__":
    main()
