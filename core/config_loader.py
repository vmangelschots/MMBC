import os
import json
from utils.logger import get_logger

def get_config_value(key: str, default=None):
    """Get a config value from /data/options.json or environment."""
    # Try options.json (Home Assistant add-on)
    try:
        with open("/data/options.json", "r") as f:
            options = json.load(f)
            if key in options:
                return options[key]
    except Exception:
        get_logger("Config").debug(f"Failed to read /data/options.json for key: {key}. Using environment value.")

    # Fallback to environment
    return os.getenv(key, default)
