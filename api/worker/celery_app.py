from celery import Celery
from celery.schedules import crontab

from api.settings import get_settings

settings = get_settings()
celery_app = Celery("shop", broker=settings.redis_url or "redis://localhost:6380/0")
celery_app.conf.update(
    task_acks_late=True,
    task_ignore_result=True,
    broker_connection_retry_on_startup=True,
    beat_schedule={
        "sync-catalog": {
            "task": "api.worker.tasks.sync_catalog_task",
            "schedule": settings.sync_interval_minutes * 60,
        },
        "sync-categories": {
            "task": "api.worker.tasks.sync_categories_task",
            "schedule": crontab(hour=3, minute=0),
        },
    },
)

from api.worker import tasks as _tasks  # noqa: E402,F401
