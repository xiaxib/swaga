from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.orm import Session

from config.settings import get_settings
from services.payment_service import MockPaymentService
from services.subscription_service import SubscriptionService
from services.usage_service import UsageService
from services.user_service import UserService
from utils.keyboards import main_menu_keyboard

router = Router()
settings = get_settings()


WELCOME_TEXT = (
    "👋 <b>Привет! Я Math Solver Bot</b>\n\n"
    "Я умею решать математические задачи по тексту и фото.\n"
    "Отправь задачу — и я верну:\n"
    "• краткий ответ,\n"
    "• пошаговое решение,\n"
    "• красивую PNG-карточку с решением.\n\n"
    "🎁 Бесплатно: 3 задачи в день.\n"
    "💎 Подписка: 199 ₽/мес"
)


@router.message(Command("start"))
async def cmd_start(message: Message, db: Session):
    user_service = UserService(db)
    is_admin = message.from_user.id in settings.admin_ids
    user_service.get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        is_admin=is_admin,
    )
    await message.answer(WELCOME_TEXT, reply_markup=main_menu_keyboard())


@router.message(Command("help"))
async def cmd_help(message: Message):
    text = (
        "📘 <b>Как пользоваться:</b>\n"
        "1) Пришли текст задачи или фото.\n"
        "2) Подожди сообщение «Решаю задачу...».\n"
        "3) Получи решение и PNG-картинку.\n\n"
        "Команды:\n"
        "/start, /help, /limits, /subscribe, /profile\n"
        "/admin_grant_sub, /admin_stats"
    )
    await message.answer(text)


@router.message(Command("limits"))
async def cmd_limits(message: Message, db: Session):
    user_service = UserService(db)
    user = user_service.get_by_telegram_id(message.from_user.id)
    if not user:
        await message.answer("Сначала нажмите /start")
        return

    usage_service = UsageService(db)
    sub_service = SubscriptionService(db)
    remaining = usage_service.get_remaining_free_requests(user.id)
    active_sub = sub_service.get_active_subscription(user.id)

    if active_sub:
        plan_text = f"💎 Подписка активна до {active_sub.expires_at.strftime('%Y-%m-%d')}"
    else:
        plan_text = "🆓 Бесплатный тариф"

    await message.answer(
        f"{plan_text}\n"
        f"Лимит в день: {settings.free_daily_limit}\n"
        f"Осталось бесплатных запросов сегодня: {remaining}"
    )


@router.message(Command("subscribe"))
async def cmd_subscribe(message: Message):
    payment = MockPaymentService().create_subscription_payment(message.from_user.id, settings.subscription_price_rub)
    await message.answer(
        "💎 <b>Подписка:</b> 199 ₽/мес\n"
        "Без лимита на задачи в период подписки.\n\n"
        f"{payment.message}"
    )


@router.message(Command("profile"))
async def cmd_profile(message: Message, db: Session):
    user_service = UserService(db)
    user = user_service.get_by_telegram_id(message.from_user.id)
    if not user:
        await message.answer("Сначала нажмите /start")
        return

    sub_service = SubscriptionService(db)
    usage_service = UsageService(db)
    sub = sub_service.get_active_subscription(user.id)
    remaining = usage_service.get_remaining_free_requests(user.id)

    await message.answer(
        "👤 <b>Профиль</b>\n"
        f"ID: {user.telegram_id}\n"
        f"Username: @{user.username or '-'}\n"
        f"Тариф: {'Подписка' if sub else 'Бесплатный'}\n"
        f"Остаток бесплатных запросов сегодня: {remaining}"
    )


@router.callback_query(F.data == "check_limit")
async def cb_check_limit(callback: CallbackQuery, db: Session):
    await cmd_limits(callback.message, db)
    await callback.answer()


@router.callback_query(F.data == "subscribe")
async def cb_subscribe(callback: CallbackQuery):
    await cmd_subscribe(callback.message)
    await callback.answer()


@router.callback_query(F.data == "send_task")
async def cb_send_task(callback: CallbackQuery):
    await callback.message.answer("Отправьте задачу текстом или фотографией 🧠")
    await callback.answer()
