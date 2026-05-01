"""Background scheduler for periodic tasks.

Runs reminder processing, backup rotation, and health checks
as recurring asyncio tasks within the FastAPI lifespan.
"""
import asyncio
import logging

logger = logging.getLogger(__name__)

# Registry of scheduled jobs: name -> (interval_seconds, coroutine_factory)
_jobs: dict[str, tuple[int, object]] = {}
_running_tasks: list[asyncio.Task] = []


def register_job(name: str, interval_seconds: int, coro_factory):
    """Register a recurring background job."""
    _jobs[name] = (interval_seconds, coro_factory)


async def _run_job(name: str, interval: int, coro_factory):
    """Run a single job on a loop with error handling."""
    while True:
        try:
            logger.info("Running scheduled job: %s", name)
            await coro_factory()
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logger.info("Job cancelled: %s", name)
            return
        except Exception:
            logger.exception("Error in scheduled job: %s", name)
            # Back off briefly before retrying
            await asyncio.sleep(60)


async def start_scheduler():
    """Start all registered background jobs."""
    for name, (interval, coro_factory) in _jobs.items():
        task = asyncio.create_task(_run_job(name, interval, coro_factory))
        _running_tasks.append(task)
        logger.info("Scheduled job '%s' every %ds", name, interval)


async def stop_scheduler():
    """Cancel all running background jobs."""
    for task in _running_tasks:
        task.cancel()
    if _running_tasks:
        await asyncio.gather(*_running_tasks, return_exceptions=True)
    _running_tasks.clear()
    logger.info("All scheduled jobs stopped")
