from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware

from database.session import SessionLocal


class DbSessionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: Dict[str, Any],
    ) -> Any:
        db = SessionLocal()
        try:
            data["db"] = db
            return await handler(event, data)
        finally:
            db.close()
