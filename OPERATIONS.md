# Operations Guide

## 매일 실행 절차
1. `python main.py --check-runtime`로 환경 상태 확인
2. `python launcher_gui.py` 실행
3. 대시보드에서 정찰/이미지/썸네일/업로드 순서로 실행
4. 감시 모드가 필요하면 `테스트 모드(감시 실행)` 사용

## 실패 Row 재처리 절차
1. 대시보드에서 실패 상태 행 확인
2. `실패 건 재실행` 또는 특정 row 옵션으로 재실행
3. 재실행 후 상태 값이 `업로드완료`로 변경됐는지 확인

## 로그 확인 방법
- 통합 앱 로그: `logs/app.log`
- 업로드 실패 로그: `logs/upload_failures.jsonl`
- 런처 JSONL 로그: 기존 `logs/launcher-YYYY-MM-DD.log` 호환 유지

## 스크린샷 확인 방법
- 실패 캡처 위치: `logs/screenshots/`
- 파일명에 row/step/timestamp가 포함되어 원인 추적 가능
