import os
from dotenv import load_dotenv
load_dotenv()
os.environ.setdefault("GRPC_DNS_RESOLVER", "native")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import articles, sources
from app.routers.admin import router as admin_router
from app.routers.users import router as users_router
from app.auth.google_oauth import router as auth_router
from app.middleware import StatsMiddleware

app = FastAPI(title="Tech News Aggregator API", version="1.0.0")

app.add_middleware(StatsMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://frontend-o3hq6ak3ka-ew.a.run.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(articles.router, prefix="/articles", tags=["articles"])
app.include_router(sources.router, prefix="/sources", tags=["sources"])
app.include_router(admin_router, prefix="/admin", tags=["admin"])
app.include_router(users_router, prefix="/users", tags=["users"])


@app.get("/health")
def health():
    return {"status": "ok"}
