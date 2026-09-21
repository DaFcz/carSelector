from pydantic import BaseModel, ConfigDict


class UserRead(BaseModel):
    """The logged-in user as the UI layer sees it - a plain value, so it
    can outlive the DB session it was loaded in (an ORM `User` can't).
    Internal to the app; not part of the REST contract in
    doc/api-contract.md, which has no auth endpoints.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    is_admin: bool
