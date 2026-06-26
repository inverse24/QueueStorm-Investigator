from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TransactionItem(BaseModel):
    transaction_id: Optional[str] = None
    timestamp: Optional[str] = None
    type: Optional[str] = None
    amount: Optional[float] = None
    counterparty: Optional[str] = None
    status: Optional[str] = None


class AnalyzeTicketRequest(BaseModel):
    ticket_id: str
    complaint: str
    language: Optional[str] = None
    channel: Optional[str] = None
    user_type: Optional[str] = None
    campaign_context: Optional[str] = None
    transaction_history: List[TransactionItem] = Field(default_factory=list)
    metadata: Optional[Dict[str, Any]] = None


class AnalyzeTicketResponse(BaseModel):
    ticket_id: Optional[str]
    relevant_transaction_id: Optional[str]
    evidence_verdict: str
    case_type: str
    severity: str
    department: str
    agent_summary: str
    recommended_next_action: str
    customer_reply: str
    human_review_required: bool
    confidence: float
    reason_codes: List[str]
