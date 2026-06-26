import json
import requests

URL = "http://127.0.0.1:8000/analyze-ticket"

with open("SUST_Preli_Sample_Cases.json", "r", encoding="utf-8") as f:
    cases = json.load(f)["cases"]

passed = 0

for i, case in enumerate(cases, 1):
    print("=" * 70)
    print(f"Test {i}: {case['id']} - {case['label']}")

    try:
        r = requests.post(URL, json=case["input"], timeout=30)
        print("HTTP:", r.status_code)

        if r.status_code != 200:
            print(r.text)
            continue

        out = r.json()
        exp = case["expected_output"]

        ok = (
            out.get("ticket_id") == exp["ticket_id"] and
            out.get("relevant_transaction_id") == exp["relevant_transaction_id"] and
            out.get("evidence_verdict") == exp["evidence_verdict"] and
            out.get("case_type") == exp["case_type"] and
            out.get("department") == exp["department"] and
            out.get("human_review_required") == exp["human_review_required"]
        )

        if ok:
            print("✅ PASS")
            passed += 1
        else:
            print("❌ FAIL")
            print("Expected:", exp)
            print("Got:", out)

    except Exception as e:
        print("ERROR:", e)

print("=" * 70)
print(f"Passed {passed}/{len(cases)}")