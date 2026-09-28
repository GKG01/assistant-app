import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from api import agent, files, health, voice
from agent.tool_registry import ToolRegistry
from config.settings import Settings
from database.database import Database
from database.repositories.files import FileRepository
from database.repositories.actions import ActionRepository
from indexer.file_indexer import FileIndexer
from permissions.manager import PermissionManager
from permissions.paths import PathPolicy
from permissions.session import DesktopSession, require_desktop_session
from services.file_search import FileSearchService
from services.file_indexing import FileIndexingService, IndexBusyError
from services.file_actions import FileActionService, WindowsFileLauncher
from tools.calculator import CalculateTool
from tools.files import SearchFilesTool, GetFileInfoTool, OpenFileTool, ShowInFolderTool


def create_app(settings: Settings | None = None, *, session_token: str | None = None) -> FastAPI:
    configuration = settings if settings is not None else Settings()
    desktop_session = DesktopSession(session_token)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        database = Database(configuration.database_path)
        database.initialize()
        policy = PathPolicy(configuration.nova_allowed_directories)
        repository = FileRepository(database)
        search = FileSearchService(repository, policy)
        actions = FileActionService(search, ActionRepository(database), WindowsFileLauncher())
        db_path = configuration.database_path.absolute()
        app.state.indexing = FileIndexingService(FileIndexer(
            policy, repository,
            (db_path, db_path.with_name(db_path.name + "-journal"),
             db_path.with_name(db_path.name + "-wal"), db_path.with_name(db_path.name + "-shm")),
        ))
        registry = ToolRegistry()
        registry.register(CalculateTool())
        for tool in (SearchFilesTool(search), GetFileInfoTool(search),
                     OpenFileTool(actions), ShowInFolderTool(actions)):
            registry.register(tool)
        app.state.database = database
        app.state.permissions = PermissionManager(registry)
        yield

    application = FastAPI(title="Nova Backend", version="0.1.0", lifespan=lifespan)
    application.state.desktop_session = desktop_session

    @application.get("/session")
    def session_status(request: Request) -> dict[str, str]:
        require_desktop_session(request)
        return {"status": "ok"}
    application.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"]
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=sorted(files.TRUSTED_ORIGINS),
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Nova-Request", "Authorization"],
    )
    for error, status, message in (
        (FileNotFoundError, 404, "File or directory no longer exists. Refresh the index."),
        (PermissionError, 403, "The path or file type is not allowed, or access was denied."),
        (ValueError, 400, "Invalid file request or allowed-directory configuration."),
        (IndexBusyError, 409, "An index refresh is already running."),
        (NotImplementedError, 501, "This action requires the Windows-native backend."),
        (sqlite3.Error, 503, "The file database is unavailable. Retry shortly."),
        (OSError, 503, "The operating system could not complete the file operation."),
    ):
        def handler(request: Request, exc: Exception, status: int = status,
                    message: str = message) -> JSONResponse:
            return JSONResponse(status_code=status, content={"detail": message})
        application.add_exception_handler(error, handler)
    for router in (health.router, agent.router, files.router, voice.router):
        application.include_router(router)
    return application


app = create_app()
