import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import load as load_config
from app.webhook.receiver import router as webhook_router
from app.worker.queue import worker_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.cfg = load_config()
    task = asyncio.create_task(worker_loop(_handle_event))
    yield
    task.cancel()


app = FastAPI(title="ci-doctor", lifespan=lifespan)
app.include_router(webhook_router)


async def _handle_event(event):
    pass


@app.get("/health")
async def health():
    return {"status": "ok"}
