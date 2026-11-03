from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_columns() -> list[str]:
    """Additively add columns that newer models have but an existing database lacks.

    New tables are created by ``Base.metadata.create_all``; this covers new columns on old
    tables so upgrading never needs to wipe the demo database. Existing data is untouched.
    Returns the list of ``table.column`` names that were added.
    """
    added: list[str] = []
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    if_not_exists = "" if engine.dialect.name == "sqlite" else "IF NOT EXISTS "
    with engine.begin() as connection:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing:
                continue
            have = {column["name"] for column in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in have or column.primary_key or column.foreign_keys:
                    continue
                default = ""
                if column.default is not None and getattr(column.default, "is_scalar", False):
                    value = column.default.arg
                    if isinstance(value, bool):
                        default = f" DEFAULT {int(value)}"
                    elif isinstance(value, (int, float)):
                        default = f" DEFAULT {value}"
                    else:
                        default = " DEFAULT '" + str(value).replace("'", "''") + "'"
                column_type = column.type.compile(dialect=engine.dialect)
                connection.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN {if_not_exists}"{column.name}" {column_type}{default}'))
                added.append(f"{table.name}.{column.name}")
    return added
