from __future__ import annotations

from src.webapp.app import create_app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("webapp:app", host="127.0.0.1", port=8000, reload=True)
