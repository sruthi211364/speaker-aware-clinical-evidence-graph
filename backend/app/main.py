from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import claims, encounters, graph, health, transcripts
from app.config import get_settings

settings = get_settings()

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(encounters.router)
app.include_router(transcripts.router)
app.include_router(claims.router)
app.include_router(graph.router)
