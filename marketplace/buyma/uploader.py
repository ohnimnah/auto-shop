"""BUYMA upload orchestration.

This module keeps browser form-filling callbacks injected from the legacy
entrypoint so behavior stays stable while orchestration moves out of
``buyma_upload.py``.
"""

from __future__ import annotations

from typing import Callable, Dict, List


def upload_products(
    *,
    specific_row: int = 0,
    upload_mode: str = "auto",
    max_items: int = 0,
    interactive: bool = True,
    get_sheets_service: Callable[[], object],
    get_sheet_name: Callable[[object], str],
    get_sheet_header_map: Callable[[object, str], Dict[str, int]],
    read_upload_rows: Callable[[object, str, int], List[Dict[str, str]]],
    setup_visible_chrome_driver: Callable[[], object],
    wait_for_buyma_login: Callable[[object], bool],
    update_cell_by_header: Callable[[object, str, int, Dict[str, int], str, str], bool],
    fill_buyma_form: Callable[[object, Dict[str, str]], str],
    handle_success_after_fill: Callable[[object, int, str, bool], tuple[bool, bool]],
    safe_input: Callable[[str], str],
    progress_status_header: str,
    status_uploading: str,
    status_completed: str,
) -> None:
    """Main upload loop for BUYMA."""
    print("바이마 출품 자동화 시작합니다\n")
    print(f"업로드 모드: {upload_mode}\n")

    service = get_sheets_service()
    sheet_name = get_sheet_name(service)
    header_map = get_sheet_header_map(service, sheet_name)
    print(f"시트: {sheet_name}")

    rows = read_upload_rows(service, sheet_name, specific_row)
    if not rows:
        print("출품 대상이 없습니다. (BUYMA URL + DB상품 + KEY 바이마판매가 필요)")
        return

    print(f"출품 행수: {len(rows)}개품\n")
    for row in rows:
        print(f"  {row['row_num']}행 {row['brand']} - {row['product_name_kr']} (JPY {row['buyma_price']})")
    print()

    driver = setup_visible_chrome_driver()
    keep_browser_open = False
    try:
        if not wait_for_buyma_login(driver):
            print("로그인 실패. 종료합니다.")
            return

        processed = 0
        for index, row_data in enumerate(rows):
            if max_items > 0 and processed >= max_items:
                break

            row_num = row_data["row_num"]
            print(f"\n{'=' * 60}")
            print(f"  [{index + 1}/{len(rows)}] {row_num}행 처리 중")
            print(f"{'=' * 60}")

            if update_cell_by_header(
                service,
                sheet_name,
                row_num,
                header_map,
                progress_status_header,
                status_uploading,
            ):
                print(f"  {row_num}행 상태 업데이트: {status_uploading}")
            processed += 1

            fill_result = fill_buyma_form(driver, row_data)

            if fill_result == "success":
                should_continue, fully_submitted = handle_success_after_fill(
                    driver,
                    row_num,
                    upload_mode,
                    interactive,
                )
                if not should_continue:
                    return
                if fully_submitted:
                    if update_cell_by_header(
                        service,
                        sheet_name,
                        row_num,
                        header_map,
                        progress_status_header,
                        status_completed,
                    ):
                        print(f"  {row_num}행 상태 업데이트: {status_completed}")
                elif upload_mode == "auto":
                    if update_cell_by_header(
                        service,
                        sheet_name,
                        row_num,
                        header_map,
                        progress_status_header,
                        "오류",
                    ):
                        print(f"  {row_num}행 상태 업데이트: 오류")
            elif fill_result == "manual_review":
                print(f"  {row_num}행은 상품명 등 수동 확인이 필요합니다. 현재 브라우저 화면을 확인해주세요.")
                keep_browser_open = True
                if interactive:
                    safe_input("  수정 또는 확인 후 Enter를 눌러주세요..")
                return
            else:
                print(f"  {row_num}행 상품입력 실패. 건너뜁니다")
                if update_cell_by_header(
                    service,
                    sheet_name,
                    row_num,
                    header_map,
                    progress_status_header,
                    "오류",
                ):
                    print(f"  {row_num}행 상태 업데이트: 오류")
                if interactive:
                    safe_input("  Enter를 눌러 다음으로 진행...")

        print(f"\n모든 상품 처리 완료! ({len(rows)}건)")

    finally:
        if keep_browser_open:
            print("\n브라우저를 열어둔 상태로 유지합니다. 확인 후 직접 닫아주세요.")
        else:
            if interactive:
                safe_input("\n브라우저를 모두 닫으면 Enter를 눌러주세요...")
            driver.quit()
            print("브라우저가 종료되었습니다.")
