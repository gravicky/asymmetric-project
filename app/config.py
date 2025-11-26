from functools import lru_cache
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "FastAPI Showcase"

    ROOT_PATH: str = "/"
    APP_PREFIX: str = "/app"
    AUTH_PREFIX: str = "/auth"
    
    SECRET_KEY: str = Field(..., description="Secret key for JWT encoding")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    CELERY_BROKER_URL: str = "amqp://username:password@host:port" # currently using rabbitmq
    CELERY_RESULT_BACKEND: str = ""

    DATABASE_URL: str = "mongodb://user_name:password@host:port/db_name?retryWrites=true&w=majority&authSource=admin"
    
    LOG_LEVEL: str = "INFO"
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )
    

@lru_cache()
def get_settings() -> Settings: # caching settings
    return Settings()


settings = get_settings()

# more settings to be present here, things like cors, ability to load from Hashicorp Vault instead of env file, etc


'''
Python dataclass can also be used as substitute of pydantic
it offers its own benefits like being slightly faster for execution 
(though pydantic is written in rust and is still very fast), 
but it has negatives like limited runtime safety compared to pydantic
'''