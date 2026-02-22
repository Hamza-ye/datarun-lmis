# backend/core/config.py
# This file is strictly for infrastructure configuration (DB URLs, keys).
# No business logic or domain models belong here.

import os

class Settings:
    PROJECT_NAME: str = "Datarun LMIS"
    # Provide a default for local development, expect to be overridden
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://dataRunApi:dataRunApi@localhost:5432/datarun_lmis")

settings = Settings()
