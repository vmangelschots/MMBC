import json
import os
from utils.logger import get_logger

logger = get_logger("Config")

def load_config():
    #config_path = "/data/options.json"
    config_path = "options.json"
    # Try loading from file (preferred)
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Error reading {config_path}: {e}")

    # Fallback: load all env vars starting with MMBC_
    logger.info("Falling back to environment variables.")
    return {k[5:]: v for k, v in os.environ.items() if k.startswith("MMBC_")}
