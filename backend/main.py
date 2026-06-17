import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from backend.routers import dashboard, signals, screening, portfolio, watchlist, alerts, trades
from backend.services.data_service import start_scheduler, scheduler

@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    if scheduler.running:
        scheduler.shutdown()

app = FastAPI(
    title="VN100 Trading System",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(signals.router, prefix="/api/v1")
app.include_router(screening.router, prefix="/api/v1")
app.include_router(portfolio.router, prefix="/api/v1")
app.include_router(watchlist.router, prefix="/api/v1")
app.include_router(alerts.router, prefix="/api/v1")
app.include_router(trades.router, prefix="/api/v1")

@app.get("/api/v1/health")
async def health():
    return {"status": "ok", "time": datetime.now().isoformat()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
