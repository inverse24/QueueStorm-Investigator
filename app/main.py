from fastapi import FastAPI

from app.schemas import AnalyzeTicketRequest, AnalyzeTicketResponse
from app.services.analyzer import analyze_ticket

app = FastAPI(title="QueueStorm Investigator API", version="1.0.0")


@app.get("/")
def root():
    return {
        "message": "QueueStorm Investigator API is running.",
        "docs": "/docs",
        "health": "/health"
    }

@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/analyze-ticket", response_model=AnalyzeTicketResponse)
def analyze_ticket_endpoint(payload: AnalyzeTicketRequest) -> AnalyzeTicketResponse:
    result = analyze_ticket(payload.model_dump())
    return AnalyzeTicketResponse(**result)
