from __future__ import annotations

def run_main_cli() -> int:
    from main import main as legacy_main

    legacy_main()
    return 0


def run_buyma_upload_cli() -> int:
    from buyma_upload import main as legacy_main

    legacy_main()
    return 0
