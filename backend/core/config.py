from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "RAG+ Platform"
    
    POSTGRES_USER: str = "rag_admin"
    POSTGRES_PASSWORD: str = "admin_pwd_123"
    POSTGRES_DB: str = "rag_platform"
    DATABASE_URL: str = "postgresql://rag_admin:admin_pwd_123@localhost:5432/rag_platform"
    
    SECRET_KEY: str = "super-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    class Config:
        env_file = "../.env"
        case_sensitive = True

settings = Settings()
