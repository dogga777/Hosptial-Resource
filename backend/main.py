from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from backend.routes.api import router as api_router

app = FastAPI(title="MediSync AI API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")

frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/app", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")


@app.get("/")
def read_root():
    return RedirectResponse(url="/app/")


@app.get("/healthz")
def health_check():
    return {"status": "ok"}