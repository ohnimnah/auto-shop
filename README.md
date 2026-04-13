# 무신사 자동화 스크립트 - 바이마 재업로드 자동화

무신사에서 구매한 상품 정보를 자동으로 Google Sheets에 입력해주는 자동화 도구입니다.

## ⚡ 빠른 시작 (5분)

### 0️⃣ 환경 자동 설치 (Python + 패키지)

운영체제별 실행 파일에서 자동으로 설치할 수 있습니다.

- Windows: `run.bat` 실행 후 `[0] 필수 자동 설치` 선택
- macOS: `run.command` 실행 후 `[0] 필수 자동 설치` 선택

직접 실행도 가능합니다.

```bash
# Windows (PowerShell)
powershell -ExecutionPolicy Bypass -File .\bootstrap_windows.ps1

# macOS
chmod +x ./bootstrap_mac.sh
./bootstrap_mac.sh
```

### 1️⃣ Google Sheets API 설정 (한 번만)

#### 1-1. Google Cloud Console에서 프로젝트 생성
```
https://console.cloud.google.com 접속
```

#### 1-2. Sheets API 활성화
- "APIs & Services" > "Library" 검색
- "Google Sheets API" 검색 후 활성화

#### 1-3. 서비스 계정 생성
1. "APIs & Services" > "Credentials"
2. "Create Credentials" > "Service Account"로 이동
3. 서비스 계정 이름 입력 (예: "auto-shop")
4. "Create and Continue"
5. 역할: "Editor" 선택
6. "Continue" > "Done"

#### 1-4. JSON 키 다운로드
1. 생성한 서비스 계정 클릭
2. "Keys" 탭
3. "Add Key" > "Create new key" > "JSON"
4. `credentials.json` 파일 자동 다운로드
5. 권장: 아래 경로에 저장
    - Windows: `%LOCALAPPDATA%\\auto_shop\\credentials.json`
    - macOS: `~/.auto_shop/credentials.json`
    - (하위호환) `auto_shop` 폴더에 둬도 동작

### 2️⃣ Google Sheets 준비

#### 2-1. 새 스프레드시트 만들기
```
https://sheets.google.com 접속
```

#### 2-2. 첫 행에 헤더 작성
```
A열: URL
B열: 상품명
C열: 가격
D열: 설명
```

#### 2-3. A열에 무신사 URL 입력
```
예시:
https://www.musinsa.com/products/1234567
https://www.musinsa.com/products/7654321
```

#### 2-4. Google Sheets 공유 (중요!)
1. "공유" 버튼 클릭
2. 서비스 계정 이메일 추가
   (credentials.json의 "client_email" 값)
3. 편집자 권한 부여

### 3️⃣ 스크립트 설정

`main.py` 파일을 텍스트 편집기에서 열기

#### 3-1. Sheets ID 입력
26줄을 찾아 수정:
```python
SPREADSHEET_ID = "YOUR_SPREADSHEET_ID_HERE"
```

ID 얻는 방법: Google Sheets 주소에서
```
https://docs.google.com/spreadsheets/d/[이 부분이 ID]/edit#gid=0
                                          ↑
                                      이 부분 복사
```

#### 3-2. 시트 이름 확인
27줄 - 일반적으로 "시트1" (확인 필요)

### 4️⃣ 실행

터미널에서:
```bash
cd auto_shop
.venv\Scripts\python.exe main.py   # Windows
# 또는
.venv/bin/python main.py            # macOS
```

로컬 데이터 폴더/자격증명 경로를 직접 지정하려면:

```bash
.venv\Scripts\python.exe main.py --data-dir C:\\auto_shop_data --credentials-file C:\\auto_shop_data\\credentials.json
```

## 📊 사용 예시

### Before (수동 입력)
```
A1: https://www.musinsa.com/products/1234567
B1: (직접 입력)
C1: (직접 입력)
D1: (직접 입력)
```

### After (자동 입력)
```
A1: https://www.musinsa.com/products/1234567
B1: 나이키 에어포스 1 백 (자동)
C1: 129000 (자동)
D1: 클래식 화이트 스니커 (자동)
```

## ⚙️ 추가 설정 (선택사항)

### 자동 가격 환율 변환

바이마는 일본 엔 기준이므로, 가격 변환을 추가하고 싶으면:

```python
# 약 1000원 = 1엔 기준
MUSINSA_PRICE = 129000
BAIMA_PRICE = 129000 // 1000  # 약 129엔
```

### 정기적 실행 (Windows Task Scheduler)

1. `task_scheduler.bat` 파일 생성:
```batch
@echo off
cd C:\Users\[USER]\iCloudDrive\auto_shop
python main.py
pause
```

2. Task Scheduler 열기
3. "기본 작업 만들기"
4. 매일 실행하도록 설정

## 🚨 문제 해결

### 401 Unauthorized 에러
- credentials.json 파일이 아래 위치 중 하나에 있는지 확인
    - `%LOCALAPPDATA%\\auto_shop\\credentials.json` (기본)
    - `--credentials-file` 인자로 지정한 경로
    - (하위호환) `auto_shop\\credentials.json`
- Google Sheets가 서비스 계정 이메일과 공유되었는지 확인

### Connection Timeout
- 무신사에서 차단되었을 가능성
- `time.sleep(2)` 값을 증가시키기 (예: 5초)

### 상품 정보가 "미확인"으로 나옴
- 무신사 웹페이지 구조가 변경되었을 가능성
- 문제 보고 (HTML 선택자 업데이트 필요)

### credentials.json 찾을 수 없음
```
FileNotFoundError: [Errno 2] No such file or directory: 'credentials.json'
```
- `%LOCALAPPDATA%\\auto_shop\\credentials.json` 또는 지정한 경로에 있는지 확인
- 파일명 철자 확인 (대소문자 구분)

## 📈 성능 팁

- **한 번에 많은 URL 처리**: 시간이 오래 걸릴 수 있음
- **배치 처리**: 10-20개씩 나누어 실행 권장
- **무신사 차단 주의**: 너무 빠르게 요청하면 IP 차단 가능

## 💡 응용 예시

### 여러 Google Sheets 동시 처리
```python
sheets_list = [
    {"id": "SHEET_ID_1", "name": "나이키"},
    {"id": "SHEET_ID_2", "name": "아디다스"},
]
```

### 바이마 자동 업로드
추후 Selenium을 사용한 바이마 자동 업로드 기능 추가 가능

## 🔗 유용한 링크
- [Google Sheets API 문서](https://developers.google.com/sheets/api)
- [무신사 쇼핑](https://www.musinsa.com)
- [바이마 판매자 가입](https://www.buyma.com)

---

**작성**: 자동화 스크립트  
**마지막 수정**: 2024년
