from api.settings import get_settings
from api.worker.tasks import run_sync_job


def build_scheduler():
    from apscheduler.schedulers.background import BackgroundScheduler

    settings = get_settings()
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_sync_job, "interval", minutes=settings.sync_interval_minutes, id="sync_catalog")
    return scheduler


def maybe_start_scheduler():
    settings = get_settings()
    if settings.sync_mode != "inprocess" or not settings.auto_sync:
        return None
    scheduler = build_scheduler()
    scheduler.start()
    return scheduler
