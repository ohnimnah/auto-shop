# Troubleshooting

## 1. Selenium 미설치
- 증상: `ModuleNotFoundError: selenium`
- 조치:
  - `python -m pip install -r requirements.txt`
  - 재검증: `python main.py --check-runtime`

## 2. ChromeDriver 문제
- 증상: 드라이버 기동 실패, 세션 생성 실패
- 조치:
  - Chrome 최신화
  - `webdriver-manager` 캐시 정리 후 재시도
  - `python main.py --check-runtime`에서 chrome/chromedriver 상태 확인

## 3. Google Credentials 문제
- 증상: 시트 접근 실패, 인증 오류
- 조치:
  - `credentials.json` 경로 확인
  - 런처 설정에서 credential 재연결
  - `--check-runtime`에서 `google_credentials` 확인

## 4. Keyring 저장 실패
- 증상: BUYMA 계정 저장 후 재시작 시 계정 없음
- 조치:
  - OS keyring/credential manager 상태 확인
  - 계정 재저장
  - 관리자 권한/보안정책 확인

## 5. BUYMA 로그인 실패
- 증상: 자동 로그인 실패/로그인 페이지 반복
- 조치:
  - 수동 로그인 후 세션 확인
  - 저장된 계정 재등록
  - 실패 로그(`logs/upload_failures.jsonl`) 확인

## 6. 이미지 다운로드 실패
- 증상: 이미지 폴더 미생성/경로 누락
- 조치:
  - 대상 URL 유효성 확인
  - 이미지 저장 경로 권한 확인
  - 재실행 후 로그 확인
