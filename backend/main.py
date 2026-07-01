"""Compatibility entrypoint for `uvicorn backend.main:app --reload`."""

from main import app


__all__ = ["app"]
