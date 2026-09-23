"""FastAPI application entrypoint."""

from fastapi import FastAPI

app = FastAPI(title="AI Requirements Conflict Detector API")


@app.get("/health")
def health_check():
    return {"status": "ok"}
