from pydantic import BaseModel, Field


class OrganizationUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
