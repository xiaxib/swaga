from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import User


class UserService:
    def __init__(self, db: Session):
        self.db = db

    def get_or_create_user(self, telegram_id: int, username: str | None, first_name: str | None, is_admin: bool) -> User:
        user = self.db.scalar(select(User).where(User.telegram_id == telegram_id))
        if user:
            # Обновляем динамические поля на случай изменений в Telegram.
            user.username = username
            user.first_name = first_name
            user.is_admin = is_admin
            self.db.commit()
            self.db.refresh(user)
            return user

        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            is_admin=is_admin,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def get_by_telegram_id(self, telegram_id: int) -> User | None:
        return self.db.scalar(select(User).where(User.telegram_id == telegram_id))
