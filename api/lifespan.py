from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from api.agent.build import build_agent
from api.agent.runs import RunRegistry
from api.db.engine import init_db
from api.settings import get_settings
from api.worker.scheduler import maybe_start_scheduler


@asynccontextmanager
async def lifespan(app):
    settings = get_settings()
    init_db(settings)
    from api.catalog.sync import ensure_vectors

    ensure_vectors()
    async with AsyncPostgresSaver.from_conn_string(settings.checkpoint_url) as checkpointer:
        await checkpointer.setup()
        app.state.checkpointer = checkpointer
        app.state.agent = build_agent(checkpointer)
        app.state.runs = RunRegistry()
        scheduler = maybe_start_scheduler()
        app.state.scheduler = scheduler
        if settings.auto_sync:
            _kick_sync()
        try:
            yield
        finally:
            if scheduler is not None:
                scheduler.shutdown(wait=False)


def _kick_sync() -> None:
    settings = get_settings()
    if settings.sync_mode == "celery":
        try:
            from api.worker.tasks import sync_catalog_task

            sync_catalog_task.delay()
        except Exception:
            return
        return
    import threading

    from api.catalog.sync import sync_catalog

    threading.Thread(target=sync_catalog, kwargs={"incremental": False}, daemon=True).start()
