# backend/core/config.py
# This file is strictly for infrastructure configuration (DB URLs, keys).
# No business logic or domain models belong here.

# backend/core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Datarun LMIS"
    # This will prioritize the system ENV, then the .env file, then this default
    DATABASE_URL: str = "postgresql+asyncpg://dataRunApi:dataRunApi@localhost:5432/datarun_lmis"

    # Tell Pydantic to look for a .env file inside the backend folder
    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8",
        extra="ignore" # Prevents crashing if .env has extra variables
    )

settings = Settings()