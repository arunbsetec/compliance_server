import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from server.core.config import settings
from server.core.ws import connection_manager
from server.db.base import Base
from server.db.session import engine
from server.models.document import Document, ExtractionField
from server.models.user import User
from server.routes.documents import router as document_router
from server.routes.user import router as user_router

_REGISTERED_MODELS = (User, Document, ExtractionField)
Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    connection_manager.set_loop(asyncio.get_running_loop())
    yield


app = FastAPI(title="Compliance Document Intelligence", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_request: Request, exc: RequestValidationError):
    errors: dict[str, str] = {}
    for error in exc.errors():
        parts = [str(part) for part in error["loc"] if part not in {"body", "query", "path"}]
        field = ".".join(parts) or "body"
        message = error["msg"].lower()
        blank = error.get("input") in (None, "")
        if error["type"] == "missing" or "required" in message or blank:
            errors[field] = f"{field} is required"
        else:
            errors[field] = f"{field} is invalid"
    return JSONResponse(status_code=422, content={"detail": errors})


app.include_router(user_router, prefix="/users", tags=["users"])
app.include_router(document_router, tags=["documents"])
