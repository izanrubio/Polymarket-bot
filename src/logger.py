"""
logger.py — Configuración del sistema de logs
"""
import sys
from loguru import logger
import config


def setup_logger():
    """Inicializa loguru con el nivel y formato adecuados."""
    logger.remove()  # Elimina el handler por defecto

    fmt = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{line}</cyan> — "
        "<level>{message}</level>"
    )

    logger.add(
        sys.stdout,
        format=fmt,
        level=config.LOG_LEVEL,
        colorize=True,
    )

    # También guarda logs en archivo (rotación diaria, máx 7 días)
    logger.add(
        "logs/polybot_{time:YYYY-MM-DD}.log",
        format=fmt,
        level="DEBUG",
        rotation="00:00",
        retention="7 days",
        colorize=False,
    )

    return logger
