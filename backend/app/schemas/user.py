from pydantic import BaseModel, EmailStr, Field

class RegisterIn(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=2, max_length=80)
    password: str = Field(min_length=6, max_length=128)

class LoginIn(BaseModel):
    email: EmailStr
    password: str

class UserOut(BaseModel):
    id: int
    email: str
    display_name: str
    favorite_genres: str
    model_config = {'from_attributes': True}

class AuthOut(BaseModel):
    token: str
    user: UserOut

class InteractionIn(BaseModel):
    content_id: int | None = None
    event_type: str
    event_value: str | None = None

class StatePatch(BaseModel):
    in_my_list: bool | None = None
    reaction: str | None = None
    progress_seconds: int | None = Field(default=None, ge=0)
