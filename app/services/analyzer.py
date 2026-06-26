import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any, Dict, List, Optional


def _should_use_gemini() -> bool:
    enabled = os.getenv("ENABLE_GEMINI_ANALYSIS", "").strip().lower()
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not enabled in {"1", "true", "yes", "on"}:
        return False
    if os.getenv("APP_ENV", "").strip().lower() in {"test", "testing"}:
        return False
    if not api_key or api_key.lower().startswith("dummy") or api_key.lower() in {"your_gemini_api_key_here", "test", "placeholder"}:
        return False
    return True


def _extract_json_payload(text: str) -> Optional[Dict[str, Any]]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", cleaned, re.S | re.I)
        if match:
            cleaned = match.group(1)
    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def _call_gemini(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not _should_use_gemini():
        return None

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    prompt = (
        "You are a customer support triage assistant. Analyze the ticket and return ONLY a JSON object "
        "with these keys: ticket_id, relevant_transaction_id, evidence_verdict, case_type, severity, "
        "department, agent_summary, recommended_next_action, customer_reply, human_review_required, "
        "confidence, reason_codes. Use the allowed enums from the task description."
        f"\nInput: {json.dumps(payload, ensure_ascii=False)}"
    )
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
    }

    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.load(response)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, json.JSONDecodeError):
        return None

    try:
        text_response = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError):
        return None

    return _extract_json_payload(text_response)


def _normalize_text(text: str) -> str:

    bangla_digits = "০১২৩৪৫৬৭৮৯"
    english_digits = "0123456789"

    table = str.maketrans(bangla_digits, english_digits)

    text = text.translate(table)

    return re.sub(r"\s+", " ", text.lower()).strip()

def _is_bangla(text: str) -> bool:
    return bool(re.search(r"[\u0980-\u09FF]", text))


def _extract_amount(text: str) -> Optional[float]:

    bangla_digits = "০১২৩৪৫৬৭৮৯"
    english_digits = "0123456789"

    text = text.translate(str.maketrans(bangla_digits, english_digits))

    match = re.search(r"\b(\d+(?:\.\d+)?)\b", text)

    if not match:
        return None

    return float(match.group(1))


def _coerce_amount(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_timestamp(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    cleaned = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(cleaned)
    except ValueError:
        return None


def _looks_like_phishing(text: str) -> bool:
    normalized = _normalize_text(text)
    phishing_keywords = [
    "otp",
    "pin",
    "password",
    "verification code",
    "called me",
    "called",
    "phone call",
    "asked for otp",
    "asked for my otp",
    "account blocked",
    "account will be blocked",
    "blocked",
    "they are from",
    "claiming to be",
    "saying they are from",
    "bkash"
]
    return any(keyword in normalized for keyword in phishing_keywords)


def _is_vague_complaint(text, history):

    normalized = _normalize_text(text)

    amount = _extract_amount(text)

    if amount is not None:
        return False

    keywords = [
        "failed",
        "refund",
        "payment",
        "cash",
        "settlement",
        "duplicate",
        "transfer",
        "sent",
        "brother",
        "didn't get",
        "did not get",
        "wrong number",
        "wrong person",
        "mistake",
    ]

    if any(k in normalized for k in keywords):
        return False

    if len(normalized.split()) > 15:
        return False

    return True
def _is_merchant_settlement(text: str, transaction_history: List[Dict[str, Any]]) -> bool:
    normalized = _normalize_text(text)
    keywords = [
        "merchant",
        "settlement",
        "sales",
        "batch",
        "settled",
        "not settled",
        "have not been settled",
        "settlement delayed",
        "sales not settled",
        "yesterday's sales",
    ]
    if not any(keyword in normalized for keyword in keywords):
        return False

    if not transaction_history:
        return False

    if any(tx.get("type") == "settlement" for tx in transaction_history):
        return True

    return False


def _is_agent_cash_in(text: str) -> bool:
    normalized = _normalize_text(text)

    bangla_terms = [
        "ক্যাশ ইন",
        "ক্যাশইন",
        "ক্যাশ-ইন",
        "এজেন্ট",
        "এজেন্টের",
        "ব্যালেন্সে",
        "ব্যালেন্সে আসেনি",
        "টাকা আসেনি",
        "ব্যালেন্স পাইনি",
        "টাকা পাইনি",
        "জমা হয়নি",
        "ক্যাশইন করেছি",
        "ক্যাশ ইন করেছি",
        "এজেন্ট বলছে",
        "টাকা পাঠিয়েছে",
        "ব্যালেন্সে টাকা আসেনি",
    ]

    english_terms = [
        "cash in",
        "cashin",
        "agent",
        "balance not reflected",
        "balance not updated",
        "money not received",
        "cash in done",
        "cash in completed",
        "cash in but balance not received",
    ]

    return any(term in normalized for term in bangla_terms + english_terms)
def _detect_duplicate_payment(transaction_history):

    payments = [
        tx for tx in transaction_history
        if tx.get("type") == "payment"
    ]

    if len(payments) < 2:
        return None

    for i in range(1, len(payments)):
        prev = payments[i-1]
        curr = payments[i]

        if (
            _coerce_amount(prev.get("amount"))
            == _coerce_amount(curr.get("amount"))
            and prev.get("counterparty")
            == curr.get("counterparty")
        ):
            t1 = _parse_timestamp(prev.get("timestamp"))
            t2 = _parse_timestamp(curr.get("timestamp"))
            if t1 and t2:
                if abs((t2 - t1).total_seconds()) > 60:
                    continue
            return curr

    return None
def _detect_ambiguous_match(complaint_text, transaction_history):
    amount = _extract_amount(complaint_text)

    if amount is None:
        return False

    candidates = [
        tx
        for tx in transaction_history
        if _coerce_amount(tx.get("amount")) == amount
    ]

    return len(candidates) >= 2

def _find_relevant_transaction(
    complaint_text: str,
    transaction_history: List[Dict[str, Any]],
    case_type: str,
) -> Optional[Dict[str, Any]]:

    if not transaction_history:
        return None

    # Duplicate payment
    if case_type == "duplicate_payment":
        return _detect_duplicate_payment(transaction_history)

    # Merchant settlement
    if case_type == "merchant_settlement_delay":
        for tx in transaction_history:
            if tx.get("type") == "settlement":
                return tx
        return transaction_history[0]

    # Agent cash-in
    if case_type == "agent_cash_in_issue":
        for tx in transaction_history:
            if (
                tx.get("type") in {"cash_in", "cash_out"}
                or str(tx.get("counterparty", "")).upper().startswith("AGENT")
            ):
                return tx
        return transaction_history[0]

    # Failed payment
    if case_type == "payment_failed":
        for tx in transaction_history:
            if tx.get("status") == "failed":
                return tx

        for tx in transaction_history:
            if tx.get("type") == "payment":
                return tx

        return transaction_history[0]

    # Match by amount
    amount = _extract_amount(complaint_text)

    if amount is not None:
        matching = [
            tx
            for tx in transaction_history
            if _coerce_amount(tx.get("amount")) == amount
        ]

        if len(matching) == 1:
            return matching[0]

        if len(matching) > 1:
            return None

    # Wrong transfer
    if case_type == "wrong_transfer":
        transfer_candidates = [
            tx
            for tx in transaction_history
            if tx.get("type") == "transfer"
        ]

        if transfer_candidates:
            return max(
                transfer_candidates,
                key=lambda tx: _parse_timestamp(tx.get("timestamp")) or datetime.min,
            )

    # Default: latest transaction
    return max(
        transaction_history,
        key=lambda tx: _parse_timestamp(tx.get("timestamp")) or datetime.min,
    )

def _detect_inconsistency(complaint_text: str, transaction_history: List[Dict[str, Any]]) -> bool:
    normalized = _normalize_text(complaint_text)
    if not transaction_history:
        return False

    if "wrong" in normalized and "person" in normalized:
        counterparty = transaction_history[0].get("counterparty")
        same_counterparty_count = sum(1 for tx in transaction_history if tx.get("counterparty") == counterparty)
        return same_counterparty_count > 1

    return False


def analyze_ticket(payload: Dict[str, Any]) -> Dict[str, Any]:
    if _should_use_gemini():
        gemini_result = _call_gemini(payload)
        if gemini_result:
            return {
                "ticket_id": gemini_result.get("ticket_id", payload.get("ticket_id")),
                "relevant_transaction_id": gemini_result.get("relevant_transaction_id"),
                "evidence_verdict": gemini_result.get("evidence_verdict", "insufficient_data"),
                "case_type": gemini_result.get("case_type", "other"),
                "severity": gemini_result.get("severity", "medium"),
                "department": gemini_result.get("department", "customer_support"),
                "agent_summary": gemini_result.get("agent_summary", ""),
                "recommended_next_action": gemini_result.get("recommended_next_action", ""),
                "customer_reply": gemini_result.get("customer_reply", ""),
                "human_review_required": bool(gemini_result.get("human_review_required", False)),
                "confidence": float(gemini_result.get("confidence", 0.7)),
                "reason_codes": list(gemini_result.get("reason_codes", [])),
            }

    complaint_text = payload.get("complaint", "")
    normalized = _normalize_text(complaint_text)
    transaction_history = payload.get("transaction_history", []) or []
    bangla = _is_bangla(complaint_text)

    case_type = "other"
    department = "customer_support"
    severity = "medium"
    human_review_required = False
    reason_codes: List[str] = []
    relevant_transaction: Optional[Dict[str, Any]] = None
    evidence_verdict = "consistent"

    if _looks_like_phishing(complaint_text):
        case_type = "phishing_or_social_engineering"
        department = "fraud_risk"
        severity = "critical"
        human_review_required = True
        reason_codes = ["phishing", "credential_protection", "critical_escalation"]
        evidence_verdict = "insufficient_data"
        relevant_transaction = None
    elif _is_merchant_settlement(complaint_text, transaction_history):
        case_type = "merchant_settlement_delay"
        department = "merchant_operations"
        severity = "medium"
        reason_codes = ["merchant_settlement", "delay", "pending"]
        relevant_transaction = _find_relevant_transaction(complaint_text, transaction_history, case_type)
    elif _is_agent_cash_in(complaint_text):
        case_type = "agent_cash_in_issue"
        department = "agent_operations"
        severity = "high"
        human_review_required = True
        reason_codes = ["agent_cash_in", "pending_transaction", "agent_ops"]
        relevant_transaction = _find_relevant_transaction(complaint_text, transaction_history, case_type)
    elif _detect_duplicate_payment(transaction_history) is not None:
        case_type = "duplicate_payment"
        department = "payments_ops"
        severity = "high"
        human_review_required = True
        reason_codes = ["duplicate_payment", "biller_verification_required"]
        relevant_transaction = _detect_duplicate_payment(transaction_history)
    elif (
    "failed" in normalized
    or "unsuccessful" in normalized
    or "balance deducted" in normalized
    or "balance was deducted" in normalized
    or "money deducted" in normalized
    or "deducted but failed" in normalized
    or "payment failed" in normalized
    or "payment unsuccessful" in normalized
    or "transaction failed" in normalized
    or "recharge failed" in normalized
    or "deducted" in normalized
    or "failed payment" in normalized
):
        case_type = "payment_failed"
        department = "payments_ops"
        severity = "high"
        reason_codes = ["payment_failed"]
        relevant_transaction = _find_relevant_transaction(complaint_text, transaction_history, case_type)
    elif (
    ("refund" in normalized or "change my mind" in normalized)
    and "failed" not in normalized
    and "deducted" not in normalized
):
        case_type = "refund_request"
        department = "customer_support"
        severity = "low"
        reason_codes = ["refund_request", "merchant_policy_dependent"]
        relevant_transaction = _find_relevant_transaction(complaint_text, transaction_history, case_type)
    elif _is_vague_complaint(complaint_text, transaction_history):
        case_type = "other"
        department = "customer_support"
        severity = "low"
        reason_codes = ["vague_complaint", "needs_clarification"]
        evidence_verdict = "insufficient_data"
        relevant_transaction = None
    elif any(x in normalized for x in [
        "wrong number",
        "wrong person",
        "mistake",
        "sent",
        "brother",
        "didn't get",
        "did not get"
    ]):
        
        case_type = "wrong_transfer"
        department = "dispute_resolution"
        severity = "high" if _extract_amount(complaint_text) and _extract_amount(complaint_text) >= 5000 else "medium"
        reason_codes = ["wrong_transfer"]
        if _detect_ambiguous_match(complaint_text, transaction_history):
            evidence_verdict = "insufficient_data"
            relevant_transaction = None
            reason_codes = ["ambiguous_match", "needs_clarification"]
            human_review_required = False
            severity = "medium"
        else:
            relevant_transaction = _find_relevant_transaction(complaint_text, transaction_history, case_type)
            if relevant_transaction is None:
                evidence_verdict = "insufficient_data"
            elif _detect_inconsistency(complaint_text, transaction_history):
                evidence_verdict = "inconsistent"
                human_review_required = True
            else:
                evidence_verdict = "consistent"
                human_review_required = True
                reason_codes.append("transaction_match")
    else:
        relevant_transaction = _find_relevant_transaction(complaint_text, transaction_history, case_type)
        if relevant_transaction is None:
            evidence_verdict = "insufficient_data"
        elif relevant_transaction.get("type") == "payment":
            reason_codes = ["payment_inquiry"]

    if case_type == "payment_failed" and "balance" in normalized:
        reason_codes.append("potential_balance_deduction")

    if case_type == "refund_request" and relevant_transaction is not None:
        reason_codes = ["refund_request", "merchant_policy_dependent"]
    if relevant_transaction is None:
        evidence_verdict = "insufficient_data"
    return {
        "ticket_id": payload.get("ticket_id"),
        "relevant_transaction_id": relevant_transaction.get("transaction_id") if relevant_transaction else None,
        "evidence_verdict": evidence_verdict,
        "case_type": case_type,
        "severity": severity,
        "department": department,
        "agent_summary": _build_agent_summary(case_type, relevant_transaction, complaint_text, bangla),
        "recommended_next_action": _build_next_action(case_type, relevant_transaction, bangla),
        "customer_reply": _build_customer_reply(case_type, relevant_transaction, bangla),
        "human_review_required": human_review_required,
        "confidence": _build_confidence(case_type, evidence_verdict),
        "reason_codes": reason_codes,
    }


def _build_agent_summary(case_type: str, relevant_transaction: Optional[Dict[str, Any]], complaint_text: str, bangla: bool) -> str:

    tx = relevant_transaction or {}
    txid = tx.get("transaction_id", "")
    amount = tx.get("amount", "")
    cp = tx.get("counterparty", "")
    status = tx.get("status", "")

    if case_type == "wrong_transfer":
        return f"Customer reports a possible wrong transfer involving {amount} BDT and transaction {txid}."

    if case_type == "payment_failed":
        return (
            f"Customer attempted a {amount} BDT payment ({txid}) which failed, "
            f"but reports balance was deducted. Requires payments operations investigation."
        )

    if case_type == "refund_request":
        return (
            "Customer requests a refund for a completed payment and needs support guidance "
            "on merchant policy."
        )

    if case_type == "phishing_or_social_engineering":
        return (
            "Customer reports an unsolicited call claiming to be from the company and asking "
            "for OTP. Customer has not yet shared credentials. Likely social engineering attempt."
        )

    if case_type == "agent_cash_in_issue":
        return (
            f"Customer reports {amount} BDT cash-in via {cp} ({txid}) "
            f"not reflected in balance. Transaction status is {status}. "
            "Agent claims funds were sent."
        )

    if case_type == "merchant_settlement_delay":
        return (
            f"Merchant reports settlement of {amount} BDT ({txid}) "
            "is delayed beyond expected window. Settlement status is pending."
        )

    if case_type == "duplicate_payment":
        return (
            f"Customer reports duplicate payment. Two identical payments detected. "
            f"The likely duplicate is transaction {txid}."
        )

    if case_type == "other":
        return (
            "Customer reports a vague concern about their money without specifying "
            "transaction, amount, or issue."
        )

    return f"Customer complaint requires manual review: {complaint_text[:120]}"
def _build_next_action(case_type: str, relevant_transaction: Optional[Dict[str, Any]], bangla: bool) -> str:
    tx = relevant_transaction or {}
    txid = tx.get("transaction_id", "")
    
    if case_type == "wrong_transfer":
        if txid:
            return f"Verify the transfer details in transaction {txid} with the customer and initiate the dispute workflow."
        return "Verify the transfer details with the customer and initiate the dispute workflow for the identified transaction."
    if case_type == "payment_failed":
        if txid:
            return f"Investigate {txid} ledger status. If balance was deducted on a failed payment, initiate the automatic reversal flow within standard SLA."
        return "Investigate the payment ledger status and reconcile any balance deduction with the payment outcome."
    if case_type == "refund_request":
        return "Explain refund eligibility based on merchant policy and direct the customer to the appropriate support channel."
    if case_type == "phishing_or_social_engineering":
        return "Escalate to fraud_risk team immediately. Confirm to customer that the company never asks for OTP. Log the reported number for fraud pattern analysis."
    if case_type == "agent_cash_in_issue":
        if txid:
            return f"Investigate transaction {txid} cash-in status with agent operations. Confirm settlement and balance reflection state."
        return "Investigate the pending cash-in status with agent operations and confirm settlement state."
    if case_type == "merchant_settlement_delay":
        if txid:
            return f"Route to merchant_operations to verify settlement batch for transaction {txid}. Communicate updated ETA if needed."
        return "Route to merchant_operations to verify settlement batch status and communicate an updated ETA if needed."
    if case_type == "duplicate_payment":
        if txid:
            return f"Verify duplicate payment. Confirm if transaction {txid} was incorrectly charged. Initiate reversal of duplicate charge within SLA."
        return "Verify the duplicate payment with payments_ops and initiate reversal if only one payment was actually accepted."
    if case_type == "other" and bangla:
        return "Customer needs to provide the transaction ID, amount, and a short description of what went wrong."
    return "Review the ticket manually and gather more information before taking action."


def _build_customer_reply(case_type: str, relevant_transaction: Optional[Dict[str, Any]], bangla: bool) -> str:

    tx = relevant_transaction or {}
    txid = tx.get("transaction_id", "")

    if case_type == "wrong_transfer":
        return (
            "We have noted your concern about the transfer. Please do not share your PIN "
            "or OTP with anyone. Our dispute team will review the case through official support channels."
        )

    if case_type == "payment_failed":
        return (
            f"We have noted that transaction {txid} may have caused an unexpected balance deduction. "
            "Our payments team will review the case and any eligible amount will be returned "
            "through official channels. Please do not share your PIN or OTP with anyone."
        )

    if case_type == "refund_request":
        return (
            "Refund eligibility depends on the merchant's own policy. "
            "Please contact the merchant directly or reply if you need guidance."
        )

    if case_type == "phishing_or_social_engineering":
        return (
            "Thank you for reaching out before sharing any information. "
            "We never ask for your PIN, OTP, or password under any circumstances. "
            "Please do not share these with anyone, even if they claim to be from us. "
            "Our fraud team has been notified of this incident."
        )

    if case_type == "agent_cash_in_issue":
        return (
            f"আপনার লেনদেন {txid} এর বিষয়ে আমরা অবগত হয়েছি। "
            "আমাদের এজেন্ট অপারেশন্স দল এটি দ্রুত যাচাই করবে এবং অফিসিয়াল চ্যানেলে আপনাকে জানাবে। "
            "অনুগ্রহ করে কারো সাথে আপনার পিন বা ওটিপি শেয়ার করবেন না।"
        )

    if case_type == "merchant_settlement_delay":
        return (
            f"We have noted your concern about settlement {txid}. "
            "Our merchant operations team will check the batch status and update you on the expected settlement time through official channels."
        )

    if case_type == "duplicate_payment":
        return (
            f"We have noted the possible duplicate payment for transaction {txid}. "
            "Our payments team will verify with the biller and any eligible amount "
            "will be returned through official channels. Please do not share your PIN or OTP with anyone."
        )

    if case_type == "other":
        if bangla:
            return (
                "ধন্যবাদ। দ্রুত সহায়তার জন্য অনুগ্রহ করে লেনদেন আইডি, পরিমাণ এবং কী সমস্যা হয়েছে তা জানান। "
                "অনুগ্রহ করে আপনার PIN বা OTP কারো সাথে শেয়ার করবেন না।"
            )

        return (
            "Thank you for reaching out. To help you faster, please share the transaction ID, "
            "the amount involved, and a short description of what went wrong. "
            "Please do not share your PIN or OTP with anyone."
        )

    return "We have received your request and will review it through official support channels."
def _build_confidence(case_type: str, evidence_verdict: str) -> float:
    if case_type == "phishing_or_social_engineering":
        return 0.95
    if case_type == "merchant_settlement_delay":
        return 0.92
    if case_type == "duplicate_payment":
        return 0.93
    if case_type == "agent_cash_in_issue":
        return 0.88
    if case_type == "payment_failed":
        return 0.9
    if case_type == "refund_request":
        return 0.85
    if case_type == "wrong_transfer":
        return 0.9 if evidence_verdict == "consistent" else 0.75 if evidence_verdict == "inconsistent" else 0.65
    if case_type == "other":
        return 0.6
    return 0.7
