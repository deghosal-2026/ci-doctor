from fastapi import APIRouter, Request, Response

from app.webhook.dedup import DedupSet
from app.webhook.verifier import verify_signature
from app.worker.queue import Event, enqueue

router = APIRouter()
dedup = DedupSet()


@router.post("/webhook")
async def webhook(request: Request):
    cfg = request.app.state.cfg
    body = await request.body()
    sig = request.headers.get("x-hub-signature-256", "")
    event_type = request.headers.get("x-github-event", "")
    event_id = request.headers.get("x-github-delivery", "")

    if not verify_signature(body, sig, cfg.github_webhook_secret):
        return Response(status_code=401)

    if dedup.seen(event_id):
        return Response(status_code=200)

    dedup.add(event_id)

    try:
        payload = await request.json()
    except Exception:
        payload = {}

    event = Event(event_id=event_id, event_type=event_type, payload=payload)
    await enqueue(event)
    return Response(status_code=200)


@router.post("/webhook/reaction")
async def reaction_webhook(request: Request):
    cfg = request.app.state.cfg
    body = await request.body()
    sig = request.headers.get("x-hub-signature-256", "")
    event_id = request.headers.get("x-github-delivery", "")

    if not verify_signature(body, sig, cfg.github_webhook_secret):
        return Response(status_code=401)

    if dedup.seen(event_id):
        return Response(status_code=200)

    dedup.add(event_id)

    try:
        payload = await request.json()
    except Exception:
        payload = {}

    event = Event(event_id=event_id, event_type="reaction", payload=payload)
    await enqueue(event)
    return Response(status_code=200)
