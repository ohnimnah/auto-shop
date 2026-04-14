"""
무신사 자동화 스크립트 - 초기 설정 도구
이 스크립트를 실행하면 main.py를 쉽게 설정할 수 있습니다
"""

import os
import sys

def setup_spreadsheet_id():
    """Google Sheets ID 설정"""
    print("\n" + "="*60)
    print("Google Sheets ID 설정")
    print("="*60)
    
    print("""
1. Google Sheets를 열기
2. 주소창에서 다음 부분을 복사:
   
   https://docs.google.com/spreadsheets/d/[여기를 복사]/edit
                                             ↑
                                      이 부분이 ID
    """)
    
    sheets_id = input("Google Sheets ID를 입력하세요: ").strip()
    
    if not sheets_id or len(sheets_id) < 20:
        print("[오류] 유효하지 않은 ID입니다")
        return None
    
    print(f"[완료] ID 저장: {sheets_id[:20]}...")
    return sheets_id

def setup_sheet_name():
    """시트 이름 설정"""
    print("\n" + "="*60)
    print("Google Sheets 시트 이름 설정")
    print("="*60)
    
    sheet_name = input("시트 이름을 입력하세요 (기본값: 시트1): ").strip()
    
    if not sheet_name:
        sheet_name = "시트1"
    
    print(f"[완료] 시트 이름: {sheet_name}")
    return sheet_name

def check_credentials():
    """credentials.json 파일 확인"""
    print("\n" + "="*60)
    print("Google API 인증 파일 확인")
    print("="*60)
    
    if os.path.exists('credentials.json'):
        print("[완료] credentials.json 파일 찾음")
        return True
    else:
        print("""
[오류] credentials.json 파일을 찾을 수 없습니다

다음 단계를 따라주세요:

1. Google Cloud Console 접속:
   https://console.cloud.google.com

2. 새 프로젝트 생성

3. Google Sheets API 활성화

4. 서비스 계정 생성:
   - APIs & Services > Credentials
   - Create Credentials > Service Account
   - Create and Continue
   - Role: Editor 선택
   - Continue > Done

5. 키 생성:
   - 생성한 서비스 계정 클릭
   - Keys 탭
   - Add Key > Create new key > JSON
   - 다운로드된 파일을 이름을 "credentials.json"으로 변경
   - 이 폴더(auto_shop)에 저장

6. 다시 이 스크립트 실행
        """)
        return False

def update_main_py(sheets_id, sheet_name):
    """main.py 파일 업데이트"""
    try:
        with open('main.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # SPREADSHEET_ID 업데이트
        content = content.replace(
            'SPREADSHEET_ID = ""',
            f'SPREADSHEET_ID = "{sheets_id}"'
        )
        
        # SHEET_NAME 업데이트
        content = content.replace(
            'SHEET_NAME = "시트1"',
            f'SHEET_NAME = "{sheet_name}"'
        )
        
        with open('main.py', 'w', encoding='utf-8') as f:
            f.write(content)
        
        print("[완료] main.py 파일 업데이트 완료")
        return True
    
    except Exception as e:
        print(f"[오류] 파일 업데이트 실패: {e}")
        return False

def test_connection():
    """Google Sheets 연결 테스트"""
    print("\n" + "="*60)
    print("Google Sheets 연결 테스트")
    print("="*60)
    
    try:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build
        
        creds = Credentials.from_service_account_file(
            'credentials.json',
            scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
        service = build('sheets', 'v4', credentials=creds)
        
        # Google Sheets ID에서 메타데이터 가져오기
        sheets_id = None
        with open('main.py', 'r', encoding='utf-8') as f:
            for line in f:
                if 'SPREADSHEET_ID = "' in line:
                    sheets_id = line.split('"')[1]
                    break
        
        if sheets_id:
            result = service.spreadsheets().get(
                spreadsheetId=sheets_id
            ).execute()
            print(f"[완료] Google Sheets 연결 성공!")
            print(f"   시트 이름: {result['properties']['title']}")
            return True
        else:
            print("[경고] SPREADSHEET_ID가 설정되지 않았습니다")
            return False
    
    except Exception as e:
        print(f"[오류] 연결 실패: {e}")
        return False

def main():
    """메인 설정 함수"""
    print("""
============================================================
무신사 자동화 스크립트 - 초기 설정 도구
============================================================
    """)
    
    # 1. credentials.json 확인
    if not check_credentials():
        return
    
    # 2. Sheets ID 설정
    sheets_id = setup_spreadsheet_id()
    if not sheets_id:
        return
    
    # 3. 시트 이름 설정
    sheet_name = setup_sheet_name()
    
    # 4. main.py 업데이트
    if not update_main_py(sheets_id, sheet_name):
        return
    
    # 5. 연결 테스트
    print("\n잠시 기다리세요...")
    if test_connection():
        print("""
============================================================
[완료] 설정 완료!
============================================================

다음 단계:

1. Google Sheets에 URL 입력:
   A열에 무신사 상품 URL을 입력하세요
   예: https://www.musinsa.com/products/1234567

2. 스크립트 실행:
   python main.py

3. 자동으로 상품 정보가 입력됩니다!

팁:
   - 처음에는 몇 개 URL로 테스트해보세요
   - 너무 많은 URL은 시간이 걸릴 수 있습니다
   - 문제가 있으면 README.md 파일을 참고하세요
        """)
    else:
        print("[경고] 설정을 다시 확인해주세요")

if __name__ == "__main__":
    main()
