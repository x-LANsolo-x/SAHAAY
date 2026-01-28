# Compatibility entrypoint for uvicorn CMD in Dockerfile.
# Keeps `uvicorn main:app` working while the actual app grows.

from services.api.app import app  # noqa: F401
