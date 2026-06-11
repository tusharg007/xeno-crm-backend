from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from config import settings


engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False}
    if settings.DATABASE_URL.startswith("sqlite")
    else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables() -> None:
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        for stmt in [
            "ALTER TABLE campaigns ADD COLUMN total_read INTEGER DEFAULT 0",
            "ALTER TABLE campaigns ADD COLUMN total_attributed_orders INTEGER DEFAULT 0",
            "ALTER TABLE campaigns ADD COLUMN total_attributed_revenue FLOAT DEFAULT 0.0",
            "ALTER TABLE messages ADD COLUMN read_at DATETIME",
            "ALTER TABLE messages ADD COLUMN attributed_order BOOLEAN DEFAULT 0",
            "ALTER TABLE messages ADD COLUMN attributed_at DATETIME",
        ]:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass
