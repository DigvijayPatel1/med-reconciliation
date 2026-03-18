from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

from app.db.database import connect_db, close_db
from app.api.routes import ingestion, reports


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_db()   # runs before the app starts accepting requests
    yield                # app runs here
    await close_db()     # runs when the app is shutting down


app = FastAPI(
    title="Medication Reconciliation & Conflict Reporting Service",
    description=(
        "Ingests medication lists from multiple clinical sources, detects conflicts, "
        "maintains a longitudinal versioned history, and surfaces unresolved conflicts "
        "for clinical review."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# Register the route groups with the /api/v1 prefix
app.include_router(ingestion.router, prefix="/api/v1")
app.include_router(reports.router,   prefix="/api/v1")


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.get("/", tags=["Health"])
async def root():
    return {"status": "ok", "service": "Medication Reconciliation API", "version": "1.0.0"}


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "healthy"}