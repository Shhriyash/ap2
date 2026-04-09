from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    agent_service_name: str = "agent-service"
    agent_host: str = "0.0.0.0"
    agent_port: int = 8000
    agent_debug: bool = True

    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "openai/gpt-4.1-mini"

    gateway_base_url: str = "http://localhost:8100"
    gateway_timeout_seconds: int = 20
    default_currency: str = "AED"

    max_pin_attempts: int = 3
    max_otp_attempts: int = 3

    model_config = SettingsConfigDict(env_file=".env.agent", env_file_encoding="utf-8")


settings = Settings()
