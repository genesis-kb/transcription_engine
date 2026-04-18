from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.database import init_db
from app.exceptions import DuplicateSourceError
from routes.curator import router as curator_router
from routes.ingestion import router as ingestion_router
from routes.media import router as media_router
from routes.transcription import router as transcription_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database on startup
    init_db()
    yield


app = FastAPI(lifespan=lifespan)

origins = [
    "http://localhost:3000",
    "https://staging-review.btctranscripts.com",
    "https://review.btctranscripts.com",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.exception_handler(DuplicateSourceError)
async def duplicate_source_exception_handler(
    request, exc: DuplicateSourceError
):
    return JSONResponse(
        status_code=409,
        content={"status": "warning", "message": str(exc)},
    )


app.include_router(transcription_router, prefix="/transcription")
app.include_router(curator_router, prefix="/curator")
app.include_router(media_router, prefix="/media")
app.include_router(ingestion_router, prefix="/ingestion")
