from fastapi import APIRouter
from sqlalchemy import text

from api.catalog.sync import get_meta
from api.db.engine import database_reachable, db_session
from api.settings import get_settings

router = APIRouter()


@router.get("/health")
def health():
    settings = get_settings()
    reachable = database_reachable()
    count = 0
    backlog = 0
    last_sync = None
    sync_status = settings.sync_mode
    if reachable:
        session = db_session()
        try:
            count = session.execute(text("SELECT count(*) FROM products")).scalar() or 0
            backlog = session.execute(text("SELECT count(*) FROM products WHERE embedding IS NULL")).scalar() or 0
            last_sync = get_meta(session, "last_sync_at")
        except Exception:
            reachable = False
        finally:
            session.close()
    if settings.sync_mode == "celery":
        try:
            import redis

            redis.Redis.from_url(settings.redis_url).ping()
        except Exception:
            sync_status = "unavailable"
    return {
        "database": "ok" if reachable else "down",
        "product_count": count,
        "catalog": "ready" if count else "loading",
        "last_sync_at": last_sync,
        "embedding_backlog": backlog,
        "sync": sync_status,
    }
