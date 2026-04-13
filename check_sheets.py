from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

creds = Credentials.from_service_account_file(
    'credentials.json',
    scopes=['https://www.googleapis.com/auth/spreadsheets']
)
service = build('sheets', 'v4', credentials=creds)
result = service.spreadsheets().get(spreadsheetId='1xFBezGKx6DmqMOnOBfWjF_zzFCsC3-KyS-bAJRyJKag').execute()
sheets = result.get('sheets', [])
print('현재 Google Sheets의 시트 이름들:')
for sheet in sheets:
    print(f'  - {sheet["properties"]["title"]}')
