import json
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

import database as db
from generator import generate_playlist
from podcasts import refresh_podcasts

logger = logging.getLogger(__name__)

_scheduler = None
JOB_PREFIX = "daily_drive_"
PODCAST_JOB = "podcast_refresh"


def get_scheduler():
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler()
    return _scheduler


def start_scheduler():
    scheduler = get_scheduler()
    _update_jobs()
    if not scheduler.running:
        scheduler.start()
        logger.info("Scheduler started")


def stop_scheduler():
    scheduler = get_scheduler()
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")


def _update_jobs():
    scheduler = get_scheduler()

    # Remove all existing daily drive jobs
    for job in scheduler.get_jobs():
        if job.id.startswith(JOB_PREFIX) or job.id == PODCAST_JOB:
            scheduler.remove_job(job.id)

    schedules_raw = db.get_setting("schedules", '[{"hour": 6, "minute": 0}]')
    try:
        schedules = json.loads(schedules_raw)
    except (json.JSONDecodeError, TypeError):
        schedules = [{"hour": 6, "minute": 0}]

    for i, sched in enumerate(schedules):
        hour = int(sched.get("hour", 6))
        minute = int(sched.get("minute", 0))

        job_id = f"{JOB_PREFIX}{i}"
        trigger = CronTrigger(hour=hour, minute=minute)

        # Generate playlist job
        scheduler.add_job(
            _run_generation,
            trigger=trigger,
            id=job_id,
            name=f"Daily Drive {hour:02d}:{minute:02d}",
            replace_existing=True,
        )
        logger.info("Scheduled daily generation at %02d:%02d", hour, minute)

    # Podcast refresh: run 15 minutes before each playlist generation
    for i, sched in enumerate(schedules):
        hour = int(sched.get("hour", 6))
        minute = int(sched.get("minute", 0)) - 15
        if minute < 0:
            minute += 60
            hour = (hour - 1) % 24

        scheduler.add_job(
            refresh_podcasts,
            trigger=CronTrigger(hour=hour, minute=minute),
            id=f"{PODCAST_JOB}_{i}",
            name=f"Podcast Refresh {hour:02d}:{minute:02d}",
            replace_existing=True,
        )
        logger.info("Scheduled podcast refresh at %02d:%02d", hour, minute)


def _run_generation():
    """Refresh podcasts first, then generate the playlist."""
    try:
        refresh_podcasts()
    except Exception as e:
        logger.exception("Podcast refresh failed before generation")
    generate_playlist()


def reschedule():
    """Reschedule all jobs with current settings."""
    _update_jobs()


def get_next_runs():
    """Get all upcoming run times."""
    scheduler = get_scheduler()
    runs = []
    for job in scheduler.get_jobs():
        if job.id.startswith(JOB_PREFIX) and job.next_run_time:
            runs.append(job.next_run_time.strftime("%Y-%m-%d %H:%M:%S"))
    runs.sort()
    return runs


def get_next_run():
    """Get the next upcoming run time."""
    runs = get_next_runs()
    return runs[0] if runs else None
