from datetime import datetime, timedelta

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from config.settings import get_settings
from database.models import Subscription, User


class SubscriptionService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def get_active_subscription(self, user_id: int) -> Subscription | None:
        now = datetime.utcnow()
        sub = self.db.scalar(
            select(Subscription)
            .where(
                Subscription.user_id == user_id,
                Subscription.is_active.is_(True),
                Subscription.expires_at > now,
            )
            .order_by(desc(Subscription.expires_at))
        )
        return sub

    def has_active_subscription(self, user_id: int) -> bool:
        return self.get_active_subscription(user_id) is not None

    def grant_subscription(self, user: User, days: int | None = None) -> Subscription:
        duration_days = days or self.settings.subscription_duration_days
        now = datetime.utcnow()
        expires_at = now + timedelta(days=duration_days)

        # Деактивируем старые подписки.
        old_subs = self.db.scalars(select(Subscription).where(Subscription.user_id == user.id)).all()
        for sub in old_subs:
            sub.is_active = False

        subscription = Subscription(
            user_id=user.id,
            plan_name="monthly",
            price=self.settings.subscription_price_rub,
            started_at=now,
            expires_at=expires_at,
            is_active=True,
        )
        self.db.add(subscription)
        self.db.commit()
        self.db.refresh(subscription)
        return subscription
