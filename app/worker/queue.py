import asyncio
from dataclasses import dataclass, field


@dataclass
class Event:
    event_id: str
    event_type: str
    payload: dict = field(default_factory=dict)


_queue: asyncio.Queue[Event] = asyncio.Queue()


async def enqueue(event: Event) -> None:
    await _queue.put(event)


async def worker_loop(handler):
    while True:
        event = await _queue.get()
        try:
            await handler(event)
        except Exception:
            pass
        finally:
            _queue.task_done()
