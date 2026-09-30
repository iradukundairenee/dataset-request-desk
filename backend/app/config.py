"""Settings read from environment variables."""
import os


class Settings:
    def __init__(self):
        self.database_url = os.environ.get(
            "DATABASE_URL", "postgresql+psycopg://desk:desk@localhost:5432/desk"
        )
        self.test_database_url = os.environ.get(
            "TEST_DATABASE_URL", "postgresql+psycopg://test:test@localhost:5433/test"
        )
        self.log_level = os.environ.get("LOG_LEVEL", "INFO")


settings = Settings()
