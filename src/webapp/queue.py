from __future__ import annotations

"""Redis queue helpers for dispatching background import jobs."""

from redis import Redis
from rq import Queue

# Queue creation is factored out mainly to keep startup code declarative and to
# give the queue boundary a single place to evolve if infrastructure changes.
def create_queue(redis_url: str, queue_name: str = "imports") -> Queue:
    """Create an RQ queue backed by the configured Redis connection."""

    connection = Redis.from_url(redis_url)
    return Queue(queue_name, connection=connection)
