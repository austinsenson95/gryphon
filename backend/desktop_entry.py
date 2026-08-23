"""Packaged desktop entry point for the Griffin FastAPI kernel."""

from __future__ import annotations

import argparse
import os


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Griffin desktop kernel")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    # Set before importing the app so pydantic-settings sees desktop defaults.
    os.environ.setdefault("GRIFFIN_RUNTIME_MODE", "desktop")
    os.environ.setdefault("HOST", args.host)
    os.environ.setdefault("PORT", str(args.port))

    import uvicorn

    from backend.main import app

    uvicorn.run(app, host=args.host, port=args.port, reload=False, log_config=None)


if __name__ == "__main__":
    main()
