from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from config.settings import get_settings
from database.models import Usage
from services.subscription_service import SubscriptionService


class UsageService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self.subscription_service = SubscriptionService(db)

    def get_today_usage(self, user_id: int) -> Usage | None:
        today = date.today()
        return self.db.scalar(select(Usage).where(Usage.user_id == user_id, Usage.date == today))

    def get_remaining_free_requests(self, user_id: int) -> int:
        usage = self.get_today_usage(user_id)
        used = usage.requests_count if usage else 0
        return max(0, self.settings.free_daily_limit - used)

    def can_make_request(self, user_id: int) -> bool:
        if self.subscription_service.has_active_subscription(user_id):
            return True
        return self.get_remaining_free_requests(user_id) > 0

    def increment_usage_if_needed(self, user_id: int) -> None:
        # Для активной подписки лимит не расходуем.
        if self.subscription_service.has_active_subscription(user_id):
            return

        today = date.today()
        usage = self.db.scalar(select(Usage).where(Usage.user_id == user_id, Usage.date == today))
        if not usage:
            usage = Usage(user_id=user_id, date=today, requests_count=1)
            self.db.add(usage)
        else:
            usage.requests_count += 1

        self.db.commit()
