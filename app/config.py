from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "banking-api"
    service_version: str = "1.0.0"
    deployment_environment: str = "demo"

    dt_endpoint_base: str = ""
    dt_api_token: str = ""

    db_url: str = "sqlite:///./banking.db"

    @property
    def traces_endpoint(self) -> str:
        return f"{self.dt_endpoint_base}/traces"

    @property
    def metrics_endpoint(self) -> str:
        return f"{self.dt_endpoint_base}/metrics"

    @property
    def logs_endpoint(self) -> str:
        return f"{self.dt_endpoint_base}/logs"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
