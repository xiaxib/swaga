from database.base import Base
from database.session import engine


def init_db() -> None:
    """Создание всех таблиц в SQLite."""
    Base.metadata.create_all(bind=engine)
