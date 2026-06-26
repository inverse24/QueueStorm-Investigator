import requests
import json

url = 'https://queuestorm-investigator-0odg.onrender.com'

# Load sample cases
with open('SUST_Preli_Sample_Cases.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

cases = data['cases']
passed = 0
failed = 0

print('='*70)
print('TESTING ALL 10 SAMPLE CASES ON LIVE ENDPOINT')
print('='*70)

for i, case in enumerate(cases, 1):
    case_id = case['id']
    label = case['label']
    input_data = case['input']
    expected = case['expected_output']
    
    try:
        response = requests.post(f'{url}/analyze-ticket', json=input_data, timeout=15)
        
        if response.status_code == 200:
            result = response.json()
            
            # Check critical fields
            checks = {
                'ticket_id': result.get('ticket_id') == expected.get('ticket_id'),
                'case_type': result.get('case_type') == expected.get('case_type'),
                'evidence_verdict': result.get('evidence_verdict') == expected.get('evidence_verdict'),
                'department': result.get('department') == expected.get('department'),
                'relevant_transaction_id': result.get('relevant_transaction_id') == expected.get('relevant_transaction_id'),
            }
            
            all_pass = all(checks.values())
            status = '✅ PASS' if all_pass else '⚠️ PARTIAL'
            
            if all_pass:
                passed += 1
            else:
                failed += 1
                
            print(f'{i}. {case_id} - {label} - {status}')
            
            if not all_pass:
                for field, check in checks.items():
                    if not check:
                        print(f'   ❌ {field}: Got {result.get(field)}, Expected {expected.get(field)}')
        else:
            print(f'{i}. {case_id} - HTTP ERROR {response.status_code}')
            failed += 1
            
    except Exception as e:
        print(f'{i}. {case_id} - ERROR: {str(e)[:50]}')
        failed += 1

print('='*70)
print(f'RESULTS: {passed} Passed, {failed} Failed out of {len(cases)} tests')
print('='*70)
