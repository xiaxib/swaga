import logging
import os


def setup_logging(level: str = "INFO") -> None:
    """Базовая настройка логирования в файл и stdout."""
    os.makedirs("logs", exist_ok=True)
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[
            logging.FileHandler("logs/bot.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
