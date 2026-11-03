from api.catalog.sync import sync_catalog, sync_categories
from api.worker.celery_app import celery_app


def run_sync_job() -> None:
    """Copy every remote product, then embed any row that does not have a vector."""
    sync_catalog(incremental=False)


@celery_app.task(name="api.worker.tasks.sync_catalog_task", bind=True, max_retries=3)
def sync_catalog_task(self):
    try:
        run_sync_job()
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2 ** self.request.retries * 30)


@celery_app.task(name="api.worker.tasks.sync_categories_task")
def sync_categories_task():
    sync_categories()
