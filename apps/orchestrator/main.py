import os
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseSettings
from dotenv import load_dotenv
load_dotenv()
class Settings(BaseSettings):
    APP_NAME: str = "Whalezchain Orchestrator"
    ENV: str = "development"
    PORT: int = 8080
    class Config:
        env_file = ".env"
settings = Settings()
app = FastAPI(title=settings.APP_NAME)
@app.get('/health')
def health():
    return {'status':'ok'}
