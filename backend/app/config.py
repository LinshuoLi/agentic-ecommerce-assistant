"""Configuration management for the application."""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings."""
    
    # Deepseek API Configuration
    deepseek_api_key: str
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    
    # Scraper Configuration
    partselect_base_url: str = "https://www.partselect.com"
    scraper_delay: float = 1.0
    max_concurrent_requests: int = 5
    
    # Application Configuration
    log_level: str = "INFO"
    api_port: int = 8000
    
    class Config:
        env_file = "../.env"  
        case_sensitive = False
        extra = "ignore"  


settings = Settings()

