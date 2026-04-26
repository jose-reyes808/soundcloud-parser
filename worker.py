from __future__ import annotations

"""Entry point for the Render background worker process."""

from pathlib import Path

from redis import Redis
from rq import Worker

from src.config import SettingsLoader

# The worker entrypoint stays intentionally boring. Operational code is easier
# to trust when it does little more than bootstrap infrastructure and yield to
# the queue runtime.
def main() -> None:
    """Start an RQ worker that listens for queued import jobs."""

    project_root = Path(__file__).resolve().parent
    settings_loader = SettingsLoader(project_root)
    web_config = settings_loader.load_web_app_config()
    redis_connection = Redis.from_url(web_config.redis_url)

    worker = Worker(["imports"], connection=redis_connection)
    worker.work()


if __name__ == "__main__":
    main()
