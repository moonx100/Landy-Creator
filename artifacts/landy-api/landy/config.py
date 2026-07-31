"""Application configuration via environment variables.

All config is loaded from the environment (or a .env file in local dev).
No secrets are hard-coded here or anywhere else in the codebase.
"""
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Deployment environment: "development", "beta", or "production".
    # Gates debug_otp — see the validator below.
    environment: str = "development"

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

    # LLM provider — uses Replit AI Integrations proxy by default.
    # Set LLM_API_KEY / LLM_BASE_URL to override with a direct provider key.
    llm_provider: str = "openai"
    llm_api_key: str = ""
    llm_model: str = "gpt-5.6-terra"
    llm_base_url: str = ""

    # Replit AI Integrations — auto-provisioned, used when llm_api_key is unset
    ai_integrations_openai_api_key: str = ""
    ai_integrations_openai_base_url: str = ""

    @property
    def effective_llm_api_key(self) -> str:
        return self.llm_api_key or self.ai_integrations_openai_api_key

    @property
    def effective_llm_base_url(self) -> str:
        return self.llm_base_url or self.ai_integrations_openai_base_url

    # Admin CLI
    admin_secret: str = "change-me-in-production"

    # Soft-delete retention window
    retention_days: int = 30

    # CORS — comma-separated origins; "*" for dev
    cors_origins: str = "*"

    # Default per-user analysis quota per period
    default_analyses_quota: int = 8

    # In dev/beta, include the OTP plaintext in the /login response so testers
    # can complete the flow without an email provider. Must be explicitly
    # opted into per-environment — never on by default, and never on in
    # production (enforced by the validator below).
    debug_otp: bool = False

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @model_validator(mode="after")
    def _forbid_debug_otp_in_production(self) -> "Settings":
        if self.environment == "production" and self.debug_otp:
            raise RuntimeError(
                "Refusing to start: ENVIRONMENT=production with DEBUG_OTP=true. "
                "debug_otp leaks plaintext OTPs in the /api/auth/login response "
                "and must never be enabled in production."
            )
        return self


settings = Settings()
