import os


os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest")
os.environ.setdefault("SESSION_SECRET_KEY", "test-session-secret-key-for-pytest")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("AUTO_CREATE_TABLES", "0")
