from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field

from linkedin_profile_api.schemas.profile import Profile


class Visibility(StrEnum):
    FULL = "full"
    LIMITED = "limited"
    OUT_OF_NETWORK = "out_of_network"
    UNKNOWN = "unknown"


class SectionState(StrEnum):
    AVAILABLE = "available"
    EMPTY = "empty"
    INACCESSIBLE = "inaccessible"
    UPSTREAM_CHANGED = "upstream_changed"
    FAILED = "failed"


class SectionName(StrEnum):
    EXPERIENCE = "experience"
    EDUCATION = "education"
    SKILLS = "skills"
    CERTIFICATIONS = "certifications"
    LANGUAGES = "languages"
    ABOUT = "about"
    IMAGES = "images"
    VOLUNTEERING = "volunteering"
    PROJECTS = "projects"
    PUBLICATIONS = "publications"
    HONORS = "honors"


class ProfileResponse(BaseModel):
    request_id: UUID
    fetched_at: datetime
    cached: bool
    deadline_hit: bool = False
    profile: Profile
    sections: dict[str, SectionState] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: UUID


class ErrorResponse(BaseModel):
    error: ErrorBody


class HealthResponse(BaseModel):
    status: str = "ok"


class ReadyResponse(BaseModel):
    ready: bool
    cache: bool
    cookies_loaded: bool
    session_outcome: str | None = None
