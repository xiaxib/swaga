from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database.models import RequestHistory, Subscription, Usage, User


class StatsService:
    def __init__(self, db: Session):
        self.db = db

    def get_basic_stats(self) -> dict:
        total_users = self.db.scalar(select(func.count(User.id))) or 0
        total_requests = self.db.scalar(select(func.count(RequestHistory.id))) or 0

        today = date.today()
        today_requests = self.db.scalar(
            select(func.coalesce(func.sum(Usage.requests_count), 0)).where(Usage.date == today)
        ) or 0

        active_subs = self.db.scalar(
            select(func.count(Subscription.id)).where(Subscription.is_active.is_(True), Subscription.expires_at > func.now())
        ) or 0

        return {
            "total_users": int(total_users),
            "total_requests": int(total_requests),
            "today_requests": int(today_requests),
            "active_subscriptions": int(active_subs),
        }
