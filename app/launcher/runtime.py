from __future__ import annotations


def run_launcher() -> None:
    """Backwards-compatible launcher entrypoint."""
    from launcher_gui import main

    main()

