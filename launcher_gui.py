"""Launcher entry point.

The dashboard UI lives in ui.dashboard. This file stays intentionally thin so
packaging scripts and existing run commands can keep importing launcher_gui.
"""

from ui.dashboard import main


if __name__ == "__main__":
    main()
