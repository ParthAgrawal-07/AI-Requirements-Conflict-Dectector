from fastapi import FastAPI, Depends, UploadFile, File, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
from .database import engine, Base, get_db
from .config import get_settings
from . import models

# Create tables for dev/tests if not using alembic immediately
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="AI Requirements Conflict Detector",
    version="0.1.0",
    description="Week 1-2 scaffold — SRS upload, auth stubs, and DB models.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ALLOWED_EXTENSIONS = (".pdf", ".docx")


# ── Health ─────────────────────────────────────────────────


@app.get("/health")
def health_check():
    return {"status": "ok"}


# ── Auth Stubs ─────────────────────────────────────────────


class UserCreate(BaseModel):
    username: str
    password: str


@app.post("/auth/register", status_code=status.HTTP_201_CREATED)
def register(user: UserCreate, db: Session = Depends(get_db)):
    """Stubbed registration — no hashing or duplicate checks yet."""
    return {"msg": "User registered successfully", "username": user.username}


@app.post("/auth/login")
def login(user: UserCreate, db: Session = Depends(get_db)):
    """Stubbed login — returns a fake JWT for frontend development."""
    return {"access_token": "fake-jwt-token", "token_type": "bearer"}


@app.get("/auth/me")
def get_me():
    """Stubbed current-user endpoint."""
    return {"username": "stub_user"}


# ── Document Upload ────────────────────────────────────────


@app.post("/documents/upload", status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...), db: Session = Depends(get_db)
):
    """
    Accept a PDF or DOCX file, validate type and size, and persist a
    Document row with status='uploaded'.

    TODO (Week 3+): requirement extraction, embeddings, LLM classification.
    """
    settings = get_settings()

    # --- Validate filename presence ---
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required.",
        )

    # --- Validate file extension ---
    if not file.filename.lower().endswith(ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # --- Validate file size ---
    contents = await file.read()
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if len(contents) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {settings.MAX_UPLOAD_SIZE_MB} MB limit.",
        )

    # --- Persist document row ---
    new_doc = models.Document(
        filename=file.filename,
        file_size=len(contents),
        status="uploaded",
    )
    db.add(new_doc)
    db.commit()
    db.refresh(new_doc)

    return {"msg": "Document uploaded successfully", "doc_id": new_doc.id}
