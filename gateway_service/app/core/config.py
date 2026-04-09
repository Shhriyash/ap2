from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    gateway_service_name: str = "gateway-service"
    gateway_host: str = "0.0.0.0"
    gateway_port: int = 8100
    gateway_debug: bool = True

    # Preferred key for this project.
    supabase_database_url: str = ""
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    # Backward-compatible fallback key.
    database_url: str = ""
    internal_service_token: str = ""
    default_currency: str = "AED"

    model_config = SettingsConfigDict(env_file="../.env.agent", env_file_encoding="utf-8", extra="ignore")

    def resolved_database_url(self) -> str:
        db_url = (self.supabase_database_url or self.database_url).strip()
        if not db_url:
            raise ValueError("Missing database URL. Set SUPABASE_DATABASE_URL in .env.agent.")
        if db_url.startswith("http://") or db_url.startswith("https://"):
            raise ValueError(
                "Invalid DB URL format. Use Supabase Postgres DSN (postgresql:// or postgresql+psycopg://), not project HTTPS URL."
            )
        if "[YOUR-PASSWORD]" in db_url or "<password>" in db_url.lower():
            raise ValueError("Database URL still has placeholder password. Replace with actual Supabase DB password.")
        if db_url.startswith("postgresql://") and "+psycopg" not in db_url:
            db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)
        return db_url


settings = Settings()
