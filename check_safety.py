import json

with open('SUST_Preli_Sample_Cases.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
    
print('SAMPLE-01 Expected Customer Reply:')
print(data['cases'][0]['expected_output']['customer_reply'])
print('\n' + '='*70 + '\n')

print('SAMPLE-03 Expected Customer Reply:')
print(data['cases'][2]['expected_output']['customer_reply'])
print('\n' + '='*70 + '\n')

print('Safety Reminders from Problem Statement:')
for reminder in data['_meta']['safety_reminders']:
    print('-', reminder)
