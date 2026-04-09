from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    gateway_service_name: str = "gateway-service"
    gateway_host: str = "0.0.0.0"
    gateway_port: int = 8100
    gateway_debug: bool = True

    database_url: str = "postgresql+psycopg://postgres:password@localhost:5432/agent_payments"
    payment_provider_mode: str = "dummy"
    external_payment_base_url: str = "https://api.example-payments.com"
    external_payment_api_key: str = ""
    external_payment_timeout_seconds: int = 20
    default_currency: str = "AED"

    model_config = SettingsConfigDict(env_file=".env.gateway", env_file_encoding="utf-8")


settings = Settings()
