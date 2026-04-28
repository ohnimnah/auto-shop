from __future__ import annotations


def run_launcher() -> None:
    """Backwards-compatible launcher entrypoint."""
    from ui.dashboard import main as dashboard_main
    dashboard_main()
