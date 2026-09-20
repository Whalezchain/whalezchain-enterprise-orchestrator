import os

from dotenv import load_dotenv
from fastapi import FastAPI

from apps.orchestrator.api import router as v1_router

load_dotenv()

APP_NAME = os.getenv("APP_NAME", "Whalezchain Orchestrator")
ENV = os.getenv("ENV", "development")
PORT = int(os.getenv("PORT", "8080"))

app = FastAPI(title=APP_NAME, version="1.0.0")
app.include_router(v1_router)


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "service": "whalezchain-enterprise-orchestrator",
        "status": "ok",
        "environment": ENV,
        "port": PORT,
    }
