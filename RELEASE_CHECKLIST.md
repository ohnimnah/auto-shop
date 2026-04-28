# Release Checklist

## 1. 설치
- `python -m pip install -r requirements.txt`
- `python -m pip install -r requirements-dev.txt`

## 2. 테스트
- `python -m unittest discover tests`
- `python -m py_compile` 전체 파이썬 파일 검증

## 3. 런타임 점검
- `python main.py --check-runtime`
- 필요 시 `python main.py --check-runtime --json`

## 4. GUI Smoke Test
- 런처 실행: `python launcher_gui.py`
- 버튼 검증:
  - 크롤링 실행
  - 이미지 다운로드
  - 썸네일 생성
  - BUYMA 업로드

## 5. BUYMA 실패 로그 확인
- `logs/upload_failures.jsonl` 생성 여부
- `logs/screenshots/` 스크린샷 생성 여부

## 6. 배포 전 Credential 확인
- Google `credentials.json` 경로 확인
- BUYMA 계정 keyring 저장 여부 확인
- 민감 파일이 배포 번들에 포함되지 않는지 확인
