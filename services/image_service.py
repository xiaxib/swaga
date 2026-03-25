import os
import textwrap
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont


class SolutionImageService:
    """Генерация PNG-карточки с решением."""

    def __init__(self, output_dir: str = "images"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def create_solution_image(self, condition: str, steps: str, final_answer: str, user_id: int) -> str:
        width = 1080
        margin = 50
        line_height = 38

        font = ImageFont.load_default()
        sections = [
            "Решение задачи",
            "",
            "Условие:",
            *self._wrap(condition, 90),
            "",
            "Шаги решения:",
            *self._wrap(steps, 90),
            "",
            "Ответ:",
            *self._wrap(final_answer, 90),
        ]

        height = max(1200, margin * 2 + len(sections) * line_height)
        image = Image.new("RGB", (width, height), color="white")
        draw = ImageDraw.Draw(image)

        y = margin
        for line in sections:
            if line == "Решение задачи":
                draw.text((margin, y), line, fill="black", font=font)
                y += line_height + 10
                continue
            draw.text((margin, y), line, fill="black", font=font)
            y += line_height

        filename = f"solution_{user_id}_{int(datetime.utcnow().timestamp())}.png"
        path = os.path.join(self.output_dir, filename)
        image.save(path, format="PNG")
        return path

    @staticmethod
    def _wrap(text: str, width: int) -> list[str]:
        lines: list[str] = []
        for raw_line in text.splitlines() or [text]:
            wrapped = textwrap.wrap(raw_line, width=width) or [""]
            lines.extend(wrapped)
        return lines
