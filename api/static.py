from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from api.settings import get_settings


def mount_spa(app: FastAPI) -> None:
    @app.get("/", include_in_schema=False)
    def spa_root():
        return _spa("")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        return _spa(full_path)


def _spa(full_path: str):
    if full_path.startswith("api") or full_path in {"docs", "redoc", "openapi.json"}:
        raise HTTPException(status_code=404)
    dist = get_settings().spa_dist
    if not dist.exists():
        raise HTTPException(status_code=404, detail="SPA build is missing")
    if full_path:
        candidate = (dist / full_path).resolve()
        root = dist.resolve()
        if candidate.is_file() and (candidate == root or root in candidate.parents):
            return FileResponse(candidate)
    index = dist / "index.html"
    if index.exists():
        return FileResponse(index)
    raise HTTPException(status_code=404)
