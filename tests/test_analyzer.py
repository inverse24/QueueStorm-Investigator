import os
import unittest
from unittest import mock

from app.services import analyzer
from app.services.analyzer import analyze_ticket


class AnalyzeTicketTests(unittest.TestCase):
    def setUp(self):
        self.env_patch = mock.patch.dict(os.environ, {"APP_ENV": "test"}, clear=False)
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)

    def test_gemini_toggle_is_enabled_when_requested(self):
        with mock.patch.dict(os.environ, {"APP_ENV": "dev", "ENABLE_GEMINI_ANALYSIS": "true", "GEMINI_API_KEY": "real-key"}, clear=False):
            self.assertTrue(analyzer._should_use_gemini())

    def test_wrong_transfer_case(self):
        payload = {
            "ticket_id": "TKT-001",
            "complaint": "I sent 5000 taka to a wrong number around 2pm today. The person isn't responding.",
            "language": "en",
            "channel": "in_app_chat",
            "user_type": "customer",
            "transaction_history": [
                {
                    "transaction_id": "TXN-9101",
                    "timestamp": "2026-04-14T14:08:22Z",
                    "type": "transfer",
                    "amount": 5000,
                    "counterparty": "+8801719876543",
                    "status": "completed",
                }
            ],
        }

        result = analyze_ticket(payload)

        self.assertEqual(result["ticket_id"], "TKT-001")
        self.assertEqual(result["case_type"], "wrong_transfer")
        self.assertEqual(result["department"], "dispute_resolution")
        self.assertTrue(result["human_review_required"])
        self.assertEqual(result["severity"], "high")

    def test_payment_failure_case(self):
        payload = {
            "ticket_id": "TKT-003",
            "complaint": "I tried to pay 1200 taka for my mobile recharge but the app showed failed. But my balance was deducted!",
            "language": "en",
            "channel": "in_app_chat",
            "user_type": "customer",
            "transaction_history": [
                {
                    "transaction_id": "TXN-9301",
                    "timestamp": "2026-04-14T16:00:00Z",
                    "type": "payment",
                    "amount": 1200,
                    "counterparty": "MERCHANT-MOBILE-OP",
                    "status": "failed",
                }
            ],
        }

        result = analyze_ticket(payload)

        self.assertEqual(result["case_type"], "payment_failed")
        self.assertEqual(result["department"], "payments_ops")
        self.assertFalse(result["human_review_required"])

    def test_refund_request_case(self):
        payload = {
            "ticket_id": "TKT-004",
            "complaint": "I paid 500 to a merchant and changed my mind. Please refund my 500 taka.",
            "language": "en",
            "channel": "in_app_chat",
            "user_type": "customer",
            "transaction_history": [
                {
                    "transaction_id": "TXN-9401",
                    "timestamp": "2026-04-14T13:00:00Z",
                    "type": "payment",
                    "amount": 500,
                    "counterparty": "MERCHANT-7821",
                    "status": "completed",
                }
            ],
        }

        result = analyze_ticket(payload)

        self.assertEqual(result["case_type"], "refund_request")
        self.assertEqual(result["department"], "customer_support")
        self.assertFalse(result["human_review_required"])

    def test_payment_failed_case_is_not_misclassified(self):
        payload = {
            "ticket_id": "TKT-003",
            "complaint": "I tried to pay 1200 taka for my mobile recharge but the app showed failed. But my balance was deducted! Please refund my money.",
            "language": "en",
            "channel": "in_app_chat",
            "user_type": "customer",
            "transaction_history": [
                {
                    "transaction_id": "TXN-9301",
                    "timestamp": "2026-04-14T16:00:00Z",
                    "type": "payment",
                    "amount": 1200,
                    "counterparty": "MERCHANT-MOBILE-OP",
                    "status": "failed",
                }
            ],
        }

        result = analyze_ticket(payload)

        self.assertEqual(result["case_type"], "payment_failed")
        self.assertEqual(result["department"], "payments_ops")

    def test_phishing_is_detected(self):
        payload = {
            "ticket_id": "TKT-005",
            "complaint": "Someone called me saying they are from bKash and asked for my OTP. They said my account will be blocked if I don't share it.",
            "language": "en",
            "channel": "call_center",
            "user_type": "customer",
            "transaction_history": [],
        }

        result = analyze_ticket(payload)

        self.assertEqual(result["case_type"], "phishing_or_social_engineering")
        self.assertEqual(result["department"], "fraud_risk")
        self.assertTrue(result["human_review_required"])

    def test_vague_complaint_has_no_transaction_match(self):
        payload = {
            "ticket_id": "TKT-006",
            "complaint": "Something is wrong with my money. Please check.",
            "language": "en",
            "channel": "in_app_chat",
            "user_type": "customer",
            "transaction_history": [
                {"transaction_id": "TXN-9601", "type": "transfer", "amount": 800, "counterparty": "+8801911223344", "status": "completed"}
            ],
        }

        result = analyze_ticket(payload)

        self.assertEqual(result["relevant_transaction_id"], None)
        self.assertEqual(result["evidence_verdict"], "insufficient_data")
        self.assertEqual(result["case_type"], "other")

    def test_bangla_agent_cash_in_is_detected(self):
        payload = {
            "ticket_id": "TKT-007",
            "complaint": "আমি আজ সকালে এজেন্টের কাছে ২০০০ টাকা ক্যাশ ইন করেছি কিন্তু আমার ব্যালেন্সে টাকা আসেনি।",
            "language": "bn",
            "channel": "call_center",
            "user_type": "customer",
            "transaction_history": [
                {"transaction_id": "TXN-9701", "type": "cash_in", "amount": 2000, "counterparty": "AGENT-318", "status": "pending"}
            ],
        }

        result = analyze_ticket(payload)

        self.assertEqual(result["case_type"], "agent_cash_in_issue")
        self.assertEqual(result["department"], "agent_operations")
        self.assertTrue(result["human_review_required"])

    def test_ambiguous_match_returns_no_transaction(self):
        payload = {
            "ticket_id": "TKT-008",
            "complaint": "I sent 1000 to my brother yesterday but he says he didn't get it. Please check.",
            "language": "en",
            "channel": "in_app_chat",
            "user_type": "customer",
            "transaction_history": [
                {"transaction_id": "TXN-9801", "type": "transfer", "amount": 1000, "counterparty": "+8801712001122", "status": "completed"},
                {"transaction_id": "TXN-9802", "type": "transfer", "amount": 1000, "counterparty": "+8801812334455", "status": "completed"},
                {"transaction_id": "TXN-9803", "type": "transfer", "amount": 1000, "counterparty": "+8801712001122", "status": "failed"},
            ],
        }

        result = analyze_ticket(payload)

        self.assertEqual(result["relevant_transaction_id"], None)
        self.assertEqual(result["evidence_verdict"], "insufficient_data")
        self.assertIn("ambiguous_match", result["reason_codes"])

    def test_merchant_settlement_delay_is_detected(self):
        payload = {
            "ticket_id": "TKT-009",
            "complaint": "I am a merchant. My yesterday's sales of 15000 taka have not been settled to my account. Settlement usually happens by 11am next day.",
            "language": "en",
            "channel": "merchant_portal",
            "user_type": "merchant",
            "transaction_history": [
                {"transaction_id": "TXN-9901", "type": "settlement", "amount": 15000, "counterparty": "MERCHANT-SELF", "status": "pending"}
            ],
        }

        result = analyze_ticket(payload)

        self.assertEqual(result["case_type"], "merchant_settlement_delay")
        self.assertEqual(result["department"], "merchant_operations")

    def test_duplicate_payment_returns_second_transaction(self):
        payload = {
            "ticket_id": "TKT-010",
            "complaint": "I paid my electricity bill 850 taka but it deducted twice from my account. Please check, I only paid once.",
            "language": "en",
            "channel": "in_app_chat",
            "user_type": "customer",
            "transaction_history": [
                {"transaction_id": "TXN-10001", "type": "payment", "amount": 850, "counterparty": "BILLER-DESCO", "status": "completed"},
                {"transaction_id": "TXN-10002", "type": "payment", "amount": 850, "counterparty": "BILLER-DESCO", "status": "completed"},
            ],
        }

        result = analyze_ticket(payload)

        self.assertEqual(result["case_type"], "duplicate_payment")
        self.assertEqual(result["relevant_transaction_id"], "TXN-10002")


if __name__ == "__main__":
    unittest.main()
