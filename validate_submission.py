#!/usr/bin/env python3
"""
Comprehensive Validation Script for QueueStorm Investigator
Checks: Requirements, Problem Statement Compliance, Safety, Enum Validation
"""

import json
import sys
from typing import Dict, List, Any, Tuple

# Load problem statement requirements
with open("SUST_Preli_Sample_Cases.json", "r", encoding="utf-8") as f:
    problem_data = json.load(f)

REQUIRED_FIELDS = problem_data["_meta"]["schema_notes"]["output_required_fields"]
ALLOWED_ENUMS = problem_data["_meta"]["allowed_enums"]
SAFETY_REMINDERS = problem_data["_meta"]["safety_reminders"]

class ValidationReport:
    def __init__(self):
        self.checks = []
        self.errors = []
        self.warnings = []
        self.pass_count = 0
        self.fail_count = 0

    def add_pass(self, msg):
        self.pass_count += 1
        self.checks.append(f"✅ {msg}")

    def add_fail(self, msg):
        self.fail_count += 1
        self.checks.append(f"❌ {msg}")
        self.errors.append(msg)

    def add_warning(self, msg):
        self.warnings.append(f"⚠️  {msg}")

    def print_report(self):
        print("\n" + "="*70)
        print("QueueStorm Investigator - Validation Report")
        print("="*70)
        
        for check in self.checks:
            print(check)
        
        if self.warnings:
            print("\n⚠️  WARNINGS:")
            for warn in self.warnings:
                print(warn)
        
        print("\n" + "="*70)
        print(f"SUMMARY: {self.pass_count} passed, {self.fail_count} failed")
        print("="*70 + "\n")
        
        return self.fail_count == 0

def validate_output_structure(output: Dict[str, Any], case_id: str) -> Tuple[bool, List[str]]:
    """Validate output schema against problem statement"""
    errors = []
    
    # Check required fields
    for field in REQUIRED_FIELDS:
        if field not in output:
            errors.append(f"{case_id}: Missing required field '{field}'")
    
    # Check enum values
    enum_checks = {
        "evidence_verdict": ALLOWED_ENUMS["evidence_verdict"],
        "case_type": ALLOWED_ENUMS["case_type"],
        "severity": ALLOWED_ENUMS["severity"],
        "department": ALLOWED_ENUMS["department"],
    }
    
    for field, allowed_values in enum_checks.items():
        if field in output and output[field] not in allowed_values:
            errors.append(
                f"{case_id}: {field}='{output[field]}' not in allowed values: {allowed_values}"
            )
    
    return len(errors) == 0, errors

def validate_safety_compliance(output: Dict[str, Any], case_id: str) -> Tuple[bool, List[str]]:
    """Check safety guidelines compliance"""
    errors = []
    customer_reply = output.get("customer_reply", "").lower()
    
    # Check for unsafe patterns
    unsafe_patterns = [
        ("PIN/OTP request", ["share your pin", "share your otp", "ask for pin", "ask for otp"]),
        ("Refund promise", ["we will refund", "you will receive", "we guarantee"]),
        ("Third-party contact", ["contact the merchant", "reach out to", "call them"]),
    ]
    
    for check_name, patterns in unsafe_patterns:
        for pattern in patterns:
            if pattern in customer_reply:
                errors.append(f"{case_id}: Safety issue - {check_name}: '{pattern}' found in customer_reply")
    
    return len(errors) == 0, errors

def validate_all_cases():
    """Run validation on all sample cases"""
    report = ValidationReport()
    
    # Load API responses
    try:
        import requests
        url = "http://127.0.0.1:8000/analyze-ticket"
    except:
        report.add_fail("Cannot connect to API - ensure server is running")
        return report
    
    # Check API health
    try:
        r = requests.get("http://127.0.0.1:8000/health")
        if r.status_code == 200:
            report.add_pass("API Health check (GET /health)")
        else:
            report.add_fail(f"API Health check failed with status {r.status_code}")
    except Exception as e:
        report.add_fail(f"Cannot reach API: {str(e)}")
        return report
    
    # Validate each case
    cases = problem_data["cases"]
    schema_passed = 0
    safety_passed = 0
    
    for case in cases:
        case_id = case["id"]
        input_data = case["input"]
        expected = case["expected_output"]
        
        # Call API
        try:
            r = requests.post(url, json=input_data, timeout=10)
            if r.status_code != 200:
                report.add_fail(f"{case_id}: API returned {r.status_code}")
                continue
            
            output = r.json()
        except Exception as e:
            report.add_fail(f"{case_id}: API call failed - {str(e)}")
            continue
        
        # Schema validation
        is_valid, errors = validate_output_structure(output, case_id)
        if is_valid:
            report.add_pass(f"{case_id}: Schema validation")
            schema_passed += 1
        else:
            report.add_fail(f"{case_id}: Schema validation")
            for err in errors:
                report.add_warning(err)
        
        # Safety compliance
        is_safe, safety_issues = validate_safety_compliance(output, case_id)
        if is_safe:
            report.add_pass(f"{case_id}: Safety guidelines compliant")
            safety_passed += 1
        else:
            report.add_fail(f"{case_id}: Safety issue detected")
            for issue in safety_issues:
                report.add_warning(issue)
        
        # Functional equivalence check
        key_fields = ["relevant_transaction_id", "evidence_verdict", "case_type", "department"]
        all_match = all(
            output.get(field) == expected.get(field) 
            for field in key_fields
        )
        if all_match:
            report.add_pass(f"{case_id}: Key fields match expected output")
        else:
            mismatches = [
                f"{field}: got '{output.get(field)}' vs expected '{expected.get(field)}'"
                for field in key_fields
                if output.get(field) != expected.get(field)
            ]
            report.add_warning(f"{case_id}: {', '.join(mismatches)}")
    
    # Summary statistics
    print("\n📊 VALIDATION STATISTICS:")
    print(f"  Schema Validation: {schema_passed}/{len(cases)} passed")
    print(f"  Safety Compliance: {safety_passed}/{len(cases)} passed")
    print(f"  Total Cases: {len(cases)}")
    
    return report

if __name__ == "__main__":
    report = validate_all_cases()
    success = report.print_report()
    sys.exit(0 if success else 1)
