from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config.settings import get_settings

settings = get_settings()
engine = create_engine(settings.db_path, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
