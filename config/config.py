"""Central configuration for FIDDS."""
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "FIDDS"
    APP_VERSION: str = "1.0.0"
    APP_DESCRIPTION: str = "Fraudulent Identity & Document Detecting System"

    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    UPLOAD_DIR: Path = BASE_DIR / "uploads"
    STATIC_DIR: Path = BASE_DIR / "static"
    TEMPLATE_DIR: Path = BASE_DIR / "templates"

    MAX_UPLOAD_MB: int = 10
    ALLOWED_EXTENSIONS: set = {".jpg", ".jpeg", ".png", ".pdf"}

    RISK_LOW_MAX: int = 30
    RISK_MEDIUM_MAX: int = 60

    TESSERACT_CMD: str = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
