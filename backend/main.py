from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from api import agent, files, health, voice
from agent.tool_registry import ToolRegistry
from config.settings import Settings
from database.database import Database
from permissions.manager import PermissionManager
from tools.calculator import CalculateTool


def create_app(settings: Settings | None = None) -> FastAPI:
    configuration = settings if settings is not None else Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database = Database(configuration.database_path)
        database.initialize()
        registry = ToolRegistry()
        registry.register(CalculateTool())
        app.state.database = database
        app.state.permissions = PermissionManager(registry)
        yield

    application = FastAPI(title="Nova Backend", version="0.1.0", lifespan=lifespan)
    application.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"]
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:1420", "http://127.0.0.1:1420",
                       "http://tauri.localhost", "https://tauri.localhost", "tauri://localhost"],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    for router in (health.router, agent.router, files.router, voice.router):
        application.include_router(router)
    return application


app = create_app()
