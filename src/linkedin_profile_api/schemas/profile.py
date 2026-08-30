from pydantic import BaseModel, Field


class ProfileImage(BaseModel):
    url: str
    width: int | None = None
    height: int | None = None
    category: str | None = None


class Experience(BaseModel):
    title: str | None = None
    company: str | None = None
    company_id: str | None = None
    company_url: str | None = None
    employment_type: str | None = None
    location: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    current: bool = False
    duration: str | None = None
    description: str | None = None
    logo: str | None = None


class Education(BaseModel):
    school: str | None = None
    degree: str | None = None
    field: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    grade: str | None = None
    activities: str | None = None
    description: str | None = None
    logo: str | None = None


class Skill(BaseModel):
    name: str
    endorsement_count: int | None = None
    related_experience: list[str] = Field(default_factory=list)


class Certification(BaseModel):
    name: str | None = None
    issuer: str | None = None
    issued: str | None = None
    expires: str | None = None
    credential_id: str | None = None
    credential_url: str | None = None
    logo: str | None = None


class Language(BaseModel):
    language: str
    proficiency: str | None = None


class Volunteering(BaseModel):
    role: str | None = None
    organization: str | None = None
    cause: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    description: str | None = None


class Project(BaseModel):
    name: str | None = None
    description: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    url: str | None = None


class Publication(BaseModel):
    title: str | None = None
    publisher: str | None = None
    date: str | None = None
    url: str | None = None
    description: str | None = None


class Honor(BaseModel):
    title: str | None = None
    issuer: str | None = None
    date: str | None = None
    description: str | None = None


class Profile(BaseModel):
    public_identifier: str
    profile_url: str
    visibility: str = "unknown"
    first_name: str | None = None
    last_name: str | None = None
    full_name: str | None = None
    headline: str | None = None
    location: str | None = None
    industry: str | None = None
    about: str | None = None
    profile_images: list[ProfileImage] = Field(default_factory=list)
    background_image: ProfileImage | None = None
    experience: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    skills: list[Skill] = Field(default_factory=list)
    certifications: list[Certification] = Field(default_factory=list)
    languages: list[Language] = Field(default_factory=list)
    volunteering: list[Volunteering] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    publications: list[Publication] = Field(default_factory=list)
    honors: list[Honor] = Field(default_factory=list)
