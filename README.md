# AI Requirements Conflict Detector

## Monorepo Setup

This repository contains the backend and frontend for the AI Requirements Conflict Detector project.

### Prerequisites
- Docker and Docker Compose
- Node.js (for local frontend dev)
- Python 3.11+ (for local backend dev)

### Running Locally (Docker Compose)
1. Copy `backend/.env.example` to `backend/.env` if needed.
2. Run `docker-compose up --build`
3. Backend API will be available at `http://localhost:8000`
4. Frontend will be available at `http://localhost:5173`

### Running Tests
**Backend**:
```bash
cd backend
pip install -r requirements.txt
pytest
```

**Frontend**:
```bash
cd frontend
npm install
npm run test
```
