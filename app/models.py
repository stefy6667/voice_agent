from pydantic import BaseModel, Field, field_validator


class ContentPayload(BaseModel):
    headline: str = Field(default="Povestea ta începe aici")
    body_text: str = Field(default="Adaugă text, poze și video pentru a personaliza experiența.")
    button_label: str = Field(default="Editează experiența")
    theme: str = Field(default="aurora")
    font_family: str = Field(default="Inter")
    text_align: str = Field(default="left")
    accent_color: str = Field(default="#7c3aed")
    text_color: str = Field(default="#f8fafc")
    video_url: str | None = None
    image_path: str | None = None

    @field_validator("theme")
    @classmethod
    def validate_theme(cls, value: str) -> str:
        allowed = {"aurora", "midnight", "sunset"}
        return value if value in allowed else "aurora"


class QRCodeRecord(BaseModel):
    qr_id: str
    edit_code: str
    slug: str
    created_at: str
    updated_at: str
    content: ContentPayload


class QRCreateResponse(BaseModel):
    qr_id: str
    edit_code: str
    slug: str
    qr_png_url: str
    public_url: str


class QRUpdateRequest(ContentPayload):
    edit_code: str = Field(min_length=4)
