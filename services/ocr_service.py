import logging
from pathlib import Path

from PIL import Image

from config.settings import get_settings

logger = logging.getLogger(__name__)


class OCRService:
    """OCR сервис с заменяемой реализацией."""

    def __init__(self):
        self.settings = get_settings()

    def extract_text(self, image_path: str) -> str:
        """Пытается распознать текст. Если OCR выключен — вернет пустую строку."""
        if not self.settings.enable_tesseract_ocr:
            return ""

        try:
            import pytesseract

            image = Image.open(Path(image_path))
            text = pytesseract.image_to_string(image, lang="rus+eng")
            return text.strip()
        except Exception as exc:  # noqa: BLE001 - для MVP важно не падать
            logger.warning("OCR error: %s", exc)
            return ""
