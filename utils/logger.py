import logging
import sys
import os
from logging.handlers import RotatingFileHandler

_logger = {}

def _setup_logger(name="mmbc"):
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter("[%(asctime)s] [%(name)s] %(levelname)s: %(message)s")

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger

def get_logger(name="mmbc"):
    global _logger
    if name not in _logger.keys():
        _logger[name] = _setup_logger(name)
    return _logger[name]