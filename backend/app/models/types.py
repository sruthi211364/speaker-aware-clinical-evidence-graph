import uuid

from sqlalchemy import Enum as SAEnum
from sqlalchemy.types import CHAR, TypeDecorator


def enum_column(python_enum, **kwargs):
    """A SQLAlchemy Enum stored as plain VARCHAR (native_enum=False) so that
    adding/renaming values later is a plain migration, not a Postgres TYPE
    migration."""
    return SAEnum(python_enum, native_enum=False, validate_strings=True, **kwargs)


class GUID(TypeDecorator):
    """Platform-independent UUID stored as CHAR(36), since we want this to
    also run against SQLite in unit tests without a Postgres dependency."""

    impl = CHAR(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if not isinstance(value, uuid.UUID):
            return str(uuid.UUID(str(value)))
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if not isinstance(value, uuid.UUID):
            return uuid.UUID(str(value))
        return value


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()
