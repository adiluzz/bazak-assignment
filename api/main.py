from fastapi import FastAPI

from api.lifespan import lifespan
from api.routes.conversations import router as conversations_router
from api.routes.health import router as health_router
from api.static import mount_spa

app = FastAPI(title="Shopping copilot", lifespan=lifespan)
app.include_router(health_router, prefix="/api")
app.include_router(conversations_router, prefix="/api")
mount_spa(app)
