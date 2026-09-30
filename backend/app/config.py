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

        # No default: refusing to start is safer than signing tokens with a known secret.
        self.jwt_secret = os.environ.get("JWT_SECRET")
        if not self.jwt_secret:
            raise RuntimeError("JWT_SECRET environment variable is not set")
        self.jwt_expiry_hours = 8


settings = Settings()
