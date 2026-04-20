"""Shared runtime path helpers for marketplace integrations."""

import os


def get_runtime_data_dir() -> str:
    """Return launcher/CLI runtime data directory."""
    env_data_dir = os.environ.get("AUTO_SHOP_DATA_DIR", "").strip()
    if env_data_dir:
        return os.path.abspath(os.path.expanduser(env_data_dir))

    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        return os.path.join(local_app_data, "auto_shop")

    return os.path.join(os.path.expanduser("~"), ".auto_shop")
