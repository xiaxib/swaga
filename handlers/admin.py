from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.orm import Session

from config.settings import get_settings
from services.stats_service import StatsService
from services.subscription_service import SubscriptionService
from services.user_service import UserService

router = Router()
settings = get_settings()


@router.message(Command("admin_grant_sub"))
async def cmd_admin_grant_sub(message: Message, db: Session):
    if message.from_user.id not in settings.admin_ids:
        await message.answer("⛔ Команда доступна только администратору.")
        return

    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Формат: /admin_grant_sub <telegram_id> [days]")
        return

    target_tg_id = int(parts[1])
    days = int(parts[2]) if len(parts) > 2 else settings.subscription_duration_days

    user_service = UserService(db)
    user = user_service.get_by_telegram_id(target_tg_id)
    if not user:
        await message.answer("Пользователь не найден. Пусть сначала нажмет /start")
        return

    sub_service = SubscriptionService(db)
    sub = sub_service.grant_subscription(user=user, days=days)
    await message.answer(
        f"✅ Подписка выдана пользователю {target_tg_id} до {sub.expires_at.strftime('%Y-%m-%d %H:%M:%S')} UTC"
    )


@router.message(Command("admin_stats"))
async def cmd_admin_stats(message: Message, db: Session):
    if message.from_user.id not in settings.admin_ids:
        await message.answer("⛔ Команда доступна только администратору.")
        return

    stats = StatsService(db).get_basic_stats()
    await message.answer(
        "📈 <b>Статистика</b>\n"
        f"Пользователей: {stats['total_users']}\n"
        f"Всего запросов: {stats['total_requests']}\n"
        f"Запросов сегодня: {stats['today_requests']}\n"
        f"Активных подписок: {stats['active_subscriptions']}"
    )
