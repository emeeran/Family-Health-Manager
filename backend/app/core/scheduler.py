"""Background scheduler for periodic tasks.

Uses APScheduler AsyncIOScheduler with a SQLite jobstore so jobs
survive process restarts. Falls back to in-process asyncio tasks
when APScheduler is unavailable.
"""
import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Registry of scheduled jobs: name -> (interval_seconds, coroutine_factory)
_jobs: dict[str, tuple[int, object]] = {}
_running_tasks: list[asyncio.Task] = []
_scheduler = None


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
    """Start all registered background jobs.

    Uses APScheduler when available; falls back to in-process asyncio tasks.
    """
    if not _jobs:
        return

    # Try APScheduler with persistent jobstore
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

        data_dir = Path("data")
        data_dir.mkdir(parents=True, exist_ok=True)
        jobstore_url = "sqlite:///data/scheduler.db"

        jobstores = {"default": SQLAlchemyJobStore(url=jobstore_url)}
        global _scheduler
        _scheduler = AsyncIOScheduler(jobstores=jobstores)

        for name, (interval, coro_factory) in _jobs.items():
            _scheduler.add_job(
                coro_factory,
                "interval",
                seconds=interval,
                id=name,
                replace_existing=True,
                misfire_grace_time=300,
            )
            logger.info("Scheduled job '%s' every %ds (APScheduler)", name, interval)

        _scheduler.start()
        logger.info("APScheduler started with SQLite jobstore")
        return
    except Exception:
        logger.warning("APScheduler unavailable — using in-process asyncio tasks")

    # Fallback: in-process asyncio tasks
    for name, (interval, coro_factory) in _jobs.items():
        task = asyncio.create_task(_run_job(name, interval, coro_factory))
        _running_tasks.append(task)
        logger.info("Scheduled job '%s' every %ds (asyncio)", name, interval)


async def stop_scheduler():
    """Cancel all running background jobs."""
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        logger.info("APScheduler stopped")
        return

    for task in _running_tasks:
        task.cancel()
    if _running_tasks:
        await asyncio.gather(*_running_tasks, return_exceptions=True)
    _running_tasks.clear()
    logger.info("All scheduled jobs stopped")
