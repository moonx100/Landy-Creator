"""Application configuration via environment variables.

All config is loaded from the environment (or a .env file in local dev).
No secrets are hard-coded here or anywhere else in the codebase.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database — required
    database_url: str

    # Session security
    session_secret: str = "change-me-in-production"
    session_ttl_hours: int = 720  # 30 days

    # Object storage (S3-compatible, e.g. MinIO, IDCloudHost IS3, Biznet Gio NEO)
    s3_endpoint_url: str = "http://minio:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket_class_b: str = "landy-contracts"  # Class B: user-uploaded contracts

    # LLM provider — must be configured explicitly via env. There is no
    # fallback provider: the app refuses to start (see landy.llm) rather than
    # silently running against an unconfigured or unintended endpoint.
    # Whatever provider/endpoint is set here must carry a documented
    # no-training and zero/short-retention data-processing guarantee and a
    # known data region — this is an operator/procurement decision, not
    # something the code can enforce; see .env.example for the checklist.
    llm_provider: str = "openai"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o"
    llm_base_url: str = ""

    # Admin CLI
    admin_secret: str = "change-me-in-production"

    # Soft-delete retention window
    retention_days: int = 30

    # CORS — comma-separated origins; "*" for dev
    cors_origins: str = "*"

    # Default per-user analysis quota per period
    default_analyses_quota: int = 8

    # In dev/beta, include the OTP plaintext in the /login response so testers
    # can complete the flow without an email provider. Set to False in production.
    debug_otp: bool = True

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
