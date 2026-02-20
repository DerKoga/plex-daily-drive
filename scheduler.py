import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

import database as db
from generator import generate_playlist

logger = logging.getLogger(__name__)

_scheduler = None


def get_scheduler():
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler()
    return _scheduler


def start_scheduler():
    scheduler = get_scheduler()
    _update_job()
    if not scheduler.running:
        scheduler.start()
        logger.info("Scheduler started")


def stop_scheduler():
    scheduler = get_scheduler()
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")


def _update_job():
    scheduler = get_scheduler()
    job_id = "daily_drive_generator"

    # Remove existing job if any
    existing = scheduler.get_job(job_id)
    if existing:
        scheduler.remove_job(job_id)

    hour = int(db.get_setting("schedule_hour", "6"))
    minute = int(db.get_setting("schedule_minute", "0"))

    trigger = CronTrigger(hour=hour, minute=minute)
    scheduler.add_job(
        generate_playlist,
        trigger=trigger,
        id=job_id,
        name="Daily Drive Playlist Generator",
        replace_existing=True,
    )
    logger.info("Scheduled daily generation at %02d:%02d", hour, minute)


def reschedule():
    """Reschedule the job with current settings."""
    _update_job()


def get_next_run():
    scheduler = get_scheduler()
    job = scheduler.get_job("daily_drive_generator")
    if job and job.next_run_time:
        return job.next_run_time.strftime("%Y-%m-%d %H:%M:%S")
    return None
