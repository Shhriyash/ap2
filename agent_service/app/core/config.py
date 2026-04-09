from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    agent_service_name: str = "agent-service"
    agent_host: str = "0.0.0.0"
    agent_port: int = 8000
    agent_debug: bool = True

    openrouter_api_key: str = ""
    openrouter_model: str = "openai/gpt-4.1-mini"
    supabase_url: str = ""
    supabase_anon_key: str = ""

    gateway_base_url: str = "http://localhost:8100"
    gateway_timeout_seconds: int = 20
    internal_service_token: str = ""
    default_currency: str = "AED"
    agent_session_ttl_minutes: int = 240

    max_pin_attempts: int = 3
    max_otp_attempts: int = 3

    model_config = SettingsConfigDict(env_file="../.env.agent", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
