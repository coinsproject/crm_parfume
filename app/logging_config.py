# -*- coding: utf-8 -*-
"""Настройки логирования"""
import logging
import os

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

# Один общий FileHandler без ротации (избегаем ошибок переименования на Windows)
file_path = os.path.join(LOG_DIR, "app.log")
file_handler = logging.FileHandler(file_path, encoding="utf-8")
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
file_handler.setFormatter(formatter)


def _get_logger(name: str, level=logging.INFO):
    logger = logging.getLogger(name)
    logger.setLevel(level)
    # добавляем хендлер один раз
    if all(getattr(h, "baseFilename", None) != file_handler.baseFilename for h in logger.handlers):
        logger.addHandler(file_handler)
    return logger

app_logger = _get_logger("app")
auth_logger = _get_logger("app.auth")
two_fa_logger = _get_logger("app.2fa")
actions_logger = _get_logger("app.actions")
price_logger = _get_logger("app.price")
partners_logger = _get_logger("app.partners")
orders_logger = _get_logger("app.orders")
