from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator


class ORMModel(BaseModel):
    """Base for response models built straight from ORM rows.

    Postgres UUID columns come back as `uuid.UUID`, and Pydantic v2 will not
    quietly coerce that into a declared `str`. Every id this API returns is a
    string, so the conversion happens once here rather than being repeated - and
    forgotten - at each call site.
    """

    model_config = ConfigDict(from_attributes=True)

    @field_validator("*", mode="before")
    @classmethod
    def _stringify_uuid(cls, value):
        if isinstance(value, UUID):
            return str(value)
        return value
