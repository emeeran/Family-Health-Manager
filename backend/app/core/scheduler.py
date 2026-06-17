"""Background scheduler for periodic tasks.

Uses APScheduler AsyncIOScheduler with a SQLite jobstore so jobs
survive process restarts. Falls back to in-process asyncio tasks
when APScheduler is unavailable.

When the app runs under multiple uvicorn workers (e.g. ``--workers 2``), the
lifespan — and therefore ``start_scheduler`` — runs in *every* worker. To stop
periodic jobs (reminders, backups, anomaly scans …) firing once per worker, we
acquire an exclusive ``fcntl`` file lock on startup; only the worker that wins
the lock actually starts the scheduler. The lock is per-process and is released
automatically on crash/exit, so a restarted worker re-acquires it cleanly.
"""
import asyncio
import logging
from pathlib import Path

try:  # POSIX-only; the deployment target is Linux.
    import fcntl
    _HAS_FCNTL = True
except ImportError:  # pragma: no cover — Windows/dev without fcntl
    fcntl = None
    _HAS_FCNTL = False

logger = logging.getLogger(__name__)

# Registry of scheduled jobs: name -> (interval_seconds, coroutine_factory)
_jobs: dict[str, tuple[int, object]] = {}
_running_tasks: list[asyncio.Task] = []
_scheduler = None

# Held for the lifetime of the winning worker to guarantee a single scheduler.
_scheduler_lock_fd = None
_SCHEDULER_LOCK_PATH = Path("data") / "scheduler.lock"


def _try_acquire_scheduler_lock() -> bool:
    """Try to grab the single-instance scheduler lock. Returns True if won.

    On failure (no fcntl, or another worker already holds it) returns False.
    Any unexpected error is logged and we return True so the scheduler still
    runs — locking is an optimisation, not a hard requirement to serve traffic.
    """
    global _scheduler_lock_fd
    if not _HAS_FCNTL:
        return True
    try:
        Path("data").mkdir(parents=True, exist_ok=True)
        fd = open(_SCHEDULER_LOCK_PATH, "w")
        try:
            fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            fd.close()
            return False
        _scheduler_lock_fd = fd
        return True
    except Exception:
        logger.exception("Could not acquire scheduler lock — running unlocked")
        return True


def _release_scheduler_lock() -> None:
    global _scheduler_lock_fd
    if _scheduler_lock_fd is not None:
        try:
            _scheduler_lock_fd.close()
        except Exception:
            pass
        _scheduler_lock_fd = None


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
    Only runs in the worker that wins the single-instance file lock.
    """
    if not _jobs:
        return

    # Single-instance guard: under multi-worker deployments only one process
    # should actually execute scheduled jobs.
    if not _try_acquire_scheduler_lock():
        logger.info("Scheduler disabled — another worker owns the lock")
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
    else:
        for task in _running_tasks:
            task.cancel()
        if _running_tasks:
            await asyncio.gather(*_running_tasks, return_exceptions=True)
        _running_tasks.clear()
        logger.info("All scheduled jobs stopped")

    # Release the single-instance lock so another worker can take over.
    _release_scheduler_lock()
