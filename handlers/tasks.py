import logging
import os

from aiogram import F, Router
from aiogram.types import FSInputFile, Message
from sqlalchemy.orm import Session

from services.history_service import HistoryService
from services.image_service import SolutionImageService
from services.ocr_service import OCRService
from services.solver_service import SolverService
from services.usage_service import UsageService
from services.user_service import UserService

router = Router()
logger = logging.getLogger(__name__)


def _render_text_result(short_answer: str, detailed_solution: str, final_answer: str) -> str:
    return (
        f"🧾 <b>Кратко:</b> {short_answer}\n\n"
        f"📚 <b>Пошаговое решение:</b>\n{detailed_solution}\n\n"
        f"✅ <b>Ответ:</b> {final_answer}"
    )


async def _handle_task(message: Message, db: Session, input_type: str, original_text: str, parsed_text: str):
    user_service = UserService(db)
    user = user_service.get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        is_admin=False,
    )

    usage_service = UsageService(db)
    if not usage_service.can_make_request(user.id):
        await message.answer(
            "🚫 Дневной лимит (3 запроса) исчерпан.\n"
            "Оформите подписку за 199 ₽/мес через /subscribe"
        )
        return

    processing_msg = await message.answer("⏳ Решаю задачу...")

    solver = SolverService()
    result = solver.solve_task(parsed_text)

    # Если OCR/текст не дал результата — просим переформулировать.
    if not result.cleaned_task.strip():
        await processing_msg.edit_text(
            "Не удалось распознать задачу. Пришлите более четкое фото или отправьте задачу текстом."
        )
        return

    usage_service.increment_usage_if_needed(user.id)

    text_result = _render_text_result(result.short_answer, result.detailed_solution, result.final_answer)
    await processing_msg.edit_text(text_result)

    image_path = SolutionImageService().create_solution_image(
        condition=result.cleaned_task,
        steps=result.detailed_solution,
        final_answer=result.final_answer,
        user_id=user.id,
    )
    await message.answer_photo(FSInputFile(image_path), caption="🖼 Готово! Вот картинка с решением.")

    HistoryService(db).save_request(
        user_id=user.id,
        input_type=input_type,
        original_text=original_text,
        parsed_text=parsed_text,
        solution_text=text_result,
    )


@router.message(F.photo)
async def handle_photo_task(message: Message, db: Session):
    photo = message.photo[-1]
    file = await message.bot.get_file(photo.file_id)

    os.makedirs("images", exist_ok=True)
    local_path = f"images/input_{message.from_user.id}_{photo.file_unique_id}.jpg"
    await message.bot.download_file(file.file_path, destination=local_path)

    ocr_text = OCRService().extract_text(local_path)
    parsed_text = (ocr_text or message.caption or "").strip()

    if not parsed_text:
        await message.answer("Не удалось распознать текст с фото. Пришлите более четкое фото или текстом.")
        return

    await _handle_task(
        message=message,
        db=db,
        input_type="photo",
        original_text=message.caption,
        parsed_text=parsed_text,
    )


@router.message(lambda m: bool(m.text) and not m.text.startswith("/"))
async def handle_text_task(message: Message, db: Session):
    text = message.text.strip()
    if not text:
        await message.answer("Пожалуйста, отправьте текст задачи.")
        return

    await _handle_task(
        message=message,
        db=db,
        input_type="text",
        original_text=text,
        parsed_text=text,
    )
