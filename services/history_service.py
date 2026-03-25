from sqlalchemy.orm import Session

from database.models import RequestHistory


class HistoryService:
    def __init__(self, db: Session):
        self.db = db

    def save_request(
        self,
        user_id: int,
        input_type: str,
        original_text: str | None,
        parsed_text: str | None,
        solution_text: str | None,
    ) -> None:
        item = RequestHistory(
            user_id=user_id,
            input_type=input_type,
            original_text=original_text,
            parsed_text=parsed_text,
            solution_text=solution_text,
        )
        self.db.add(item)
        self.db.commit()
