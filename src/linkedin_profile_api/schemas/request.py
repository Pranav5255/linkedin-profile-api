from pydantic import BaseModel, Field


class ProfileRequest(BaseModel):
    profile_url: str = Field(min_length=1, max_length=512)
