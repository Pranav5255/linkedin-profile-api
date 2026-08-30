from pydantic import BaseModel, Field


class ProfileRequest(BaseModel):
    profile_url: str = Field(min_length=1, max_length=512)
    linkedin_cookie: str | None = Field(
        default=None,
        max_length=32_768,
        description=(
            "Optional full LinkedIn Cookie header for this request only. "
            "Must include li_at and JSESSIONID. Prefer X-LinkedIn-Cookie."
        ),
    )
