import logging
import re
from dataclasses import dataclass

from sympy import Eq, SympifyError, symbols
from sympy.parsing.sympy_parser import parse_expr
from sympy.solvers import solve

logger = logging.getLogger(__name__)


@dataclass
class SolverResult:
    cleaned_task: str
    short_answer: str
    detailed_solution: str
    final_answer: str


class SolverAdapter:
    """Интерфейс адаптера AI-решателя."""

    def solve(self, task_text: str) -> SolverResult:
        raise NotImplementedError


class LocalMathSolverAdapter(SolverAdapter):
    """Простой локальный solver для MVP (без платных API)."""

    math_keywords = {
        "+", "-", "*", "/", "=", "x", "y", "z", "уравн", "процент", "дроб", "система", "неравен", "производн"
    }

    def solve(self, task_text: str) -> SolverResult:
        cleaned = self._clean_text(task_text)
        if not self._is_math_task(cleaned):
            return SolverResult(
                cleaned_task=cleaned,
                short_answer="Похоже, это не математическая задача.",
                detailed_solution="Я решаю только математические задачи. Пожалуйста, пришлите задачу по математике.",
                final_answer="Нет математического выражения для решения.",
            )

        try:
            return self._solve_simple_equation(cleaned)
        except Exception as exc:  # noqa: BLE001 - fallback обязателен для UX
            logger.warning("Solver fallback triggered: %s", exc)
            return SolverResult(
                cleaned_task=cleaned,
                short_answer="Задача принята, но не удалось автоматически решить точно.",
                detailed_solution=(
                    "1) Я выделил условие задачи.\n"
                    "2) Попробовал применить локальный математический решатель.\n"
                    "3) Для этой формулировки нужен более продвинутый AI-адаптер.\n"
                    "4) Переформулируйте задачу короче или пришлите текстом с явными знаками."
                ),
                final_answer="Нужна уточненная формулировка задачи.",
            )

    @staticmethod
    def _clean_text(text: str) -> str:
        text = text.replace("\n", " ").strip()
        text = re.sub(r"\s+", " ", text)
        return text

    def _is_math_task(self, text: str) -> bool:
        lower = text.lower()
        if any(keyword in lower for keyword in self.math_keywords):
            return True
        return bool(re.search(r"\d", lower))

    def _solve_simple_equation(self, cleaned: str) -> SolverResult:
        # Поддержка базовых выражений и уравнений вида 2*x+3=7.
        normalized = cleaned.replace("^", "**").replace(",", ".")
        x = symbols("x")

        if "=" in normalized:
            left, right = normalized.split("=", maxsplit=1)
            left_expr = parse_expr(left)
            right_expr = parse_expr(right)
            equation = Eq(left_expr, right_expr)
            solutions = solve(equation, x)

            detailed = (
                f"1) Исходное уравнение: {left.strip()} = {right.strip()}\n"
                f"2) Приводим к символьному виду: {equation}\n"
                f"3) Решаем уравнение относительно x.\n"
                f"4) Получаем: x = {solutions}"
            )
            return SolverResult(
                cleaned_task=cleaned,
                short_answer=f"Найдено решение: x = {solutions}",
                detailed_solution=detailed,
                final_answer=f"x = {solutions}",
            )

        try:
            value = parse_expr(normalized)
        except SympifyError:
            value = parse_expr(re.sub(r"[^0-9+\-*/(). ]", "", normalized))

        detailed = (
            f"1) Выражение: {cleaned}\n"
            f"2) Вычисляем значение выражения.\n"
            f"3) Результат: {value}"
        )
        return SolverResult(
            cleaned_task=cleaned,
            short_answer=f"Ответ: {value}",
            detailed_solution=detailed,
            final_answer=str(value),
        )


class SolverService:
    """Фасад для решателя с заменяемым адаптером (LLM/API можно подключить позже)."""

    def __init__(self, adapter: SolverAdapter | None = None):
        self.adapter = adapter or LocalMathSolverAdapter()

    def solve_task(self, task_text: str) -> SolverResult:
        return self.adapter.solve(task_text)
