# 무신사→바이마 자동화 - 빠른 참조

## 📋 체크리스트

### 초기 설정 (한 번만)
- [ ] Google Cloud Console에서 프로젝트 생성
- [ ] Google Sheets API 활성화
- [ ] 서비스 계정 생성
- [ ] credentials.json 다운로드 및 auto_shop 폴더에 저장
- [ ] Google Sheets 생성 및 헤더 작성 (URL | 상품명 | 가격 | 설명)
- [ ] 서비스 계정 이메일과 Google Sheets 공유
- [ ] `python setup.py` 실행하여 설정 완료

### 사용 시작
- [ ] A열에 무신사 URL 입력
- [ ] `python main.py` 실행
- [ ] 자동으로 상품 정보 입력됨

## 🚀 빠른 시작 명령어

```bash
# 폴더 이동
cd c:\Users\[USER]\iCloudDrive\auto_shop

# 환경 자동 설치 (Python + 패키지)
# Windows
powershell -ExecutionPolicy Bypass -File .\bootstrap_windows.ps1

# macOS
chmod +x ./bootstrap_mac.sh
./bootstrap_mac.sh

# 초기 설정 (처음 한 번)
.venv\Scripts\python.exe setup.py   # Windows
# 또는
.venv/bin/python setup.py            # macOS

# 자동화 실행
.venv\Scripts\python.exe main.py    # Windows
# 또는
.venv/bin/python main.py             # macOS

# 또는 단순히
.\run.bat
```

## 📍 파일 구조

```
auto_shop/
├── requirements.txt      # Python 패키지 목록
├── bootstrap_windows.ps1 # Windows 자동 설치
├── bootstrap_mac.sh      # macOS 자동 설치
├── main.py              # 메인 자동화 스크립트
├── setup.py             # 초기 설정 도구
├── run.bat              # Windows 빠른 실행 파일
├── run.command          # macOS 빠른 실행 파일
├── credentials.json     # Google API 인증 파일 (직접 다운로드)
├── README.md            # 상세 가이드
├── docs/ADVANCED.md     # 고급 설정
├── docs/QUICK_REF.md    # 이 파일
└── images/              # 예시 이미지
```

## 🔗 Google Sheets ID 찾기

Google Sheets 주소:
```
https://docs.google.com/spreadsheets/d/HERE_IS_ID/edit#gid=0
                                       ↑ 여기를 복사
```

## 🎯 주요 기능

| 기능 | 설명 |
|------|------|
| URL 입력 | A열에 무신사 상품 URL 입력 |
| 상품명 추출 | B열에 자동 입력 |
| 가격 추출 | C열에 자동 입력 |
| 설명 추출 | D열에 자동 입력 |
| 자동 저장 | Google Sheets에 실시간 저장 |

## ⚡ 사용 흐름도

```
1. URL 입력 (A열)
        ↓
2. main.py 실행
        ↓
3. 각 URL 크롤링
        ↓
4. Google Sheets에 입력
        ↓
5. 완료!
```

## 🆘 일반적인 문제 해결

| 문제 | 해결 방법 |
|------|----------|
| `credentials.json` 미발견 | Google Cloud Console에서 다운로드 후 폴더에 저장 |
| 401 Unauthorized | Google Sheets가 서비스 계정과 공유되었는지 확인 |
| Connection Timeout | 무신사에서 차단됨 - `time.sleep(2)` 증가 |
| 상품 정보 "미확인" | 무신사 웹페이지 구조 변경 - HTML 선택자 업데이트 필요 |
| 느린 속도 | 배치처리 나누기 또는 20개 이상 한 번에 X |

## 💡 팁 & 트릭

### 몇 개만 테스트하기
```
1. A2-A4 셀에만 URL 입력
2. main.py 실행
3. 정상 작동 확인 후 추가 URL 입력
```

### 자동 실행 예약 (Windows)
```
1. run.bat을 task scheduler에 등록
2. 매일 특정 시간에 자동 실행
3. 시간 절약!
```

### Google Sheets 자동 새로고침
```
Ctrl + Shift + F9 (또는 도구 → 자동 새로고침)
```

## 📊 예상 소요 시간

| 작업 | 시간 |
|------|------|
| 초기 설정 | 10-15분 |
| 10개 URL 처리 | 1-2분 |
| 50개 URL 처리 | 5-10분 |
| 100개 URL 처리 | 10-20분 |

## 🎯 다음 단계

### 1단계: 테스트
```python
1-2개 URL로 테스트
→ 상품 정보가 정확히 입력되는지 확인
```

### 2단계: 배치 처리
```python
10-20개 URL씩 나누어 처리
→ 안정성 확보
```

### 3단계: 자동화
```python
Task Scheduler에 등록
→ 매일 자동 실행
```

### 4단계: 바이마 연동 (선행)
```python
향후 추가: Selenium을 사용한 바이마 자동 업로드
```

## 🔒 보안 체크리스트

- [ ] credentials.json을 공개 저장소에 커밋하지 않음
- [ ] `.gitignore` 파일에 `credentials.json` 추가
- [ ] 비밀번호 등 민감한 정보를 코드에 넣지 않음
- [ ] API 제한 설정 (선택사항): Google Cloud Console

## 📞 지원 매뉴얼

### README.md
→ 기본 사용법 및 설명

### docs/ADVANCED.md
→ 고급 설정 및 커스터마이징

### main.py
→ 주석 확인 (코드 설명)

---

**마지막 업데이트**: 2024년  
**버전**: 1.0  
**상태**: 안정 버전 ✅
