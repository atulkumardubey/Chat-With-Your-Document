import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _get(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if value is None:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


@dataclass(frozen=True)
class Settings:
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str

    nvidia_api_key: str
    nvidia_base_url: str
    nvidia_llm_model: str
    nvidia_vision_model: str

    embedding_model_name: str
    embedding_dim: int

    default_chunk_strategy: str
    default_excel_format: str
    top_k: int
    similarity_threshold: float

    frontend_origin: str


def get_settings() -> Settings:
    return Settings(
        db_host=_get("DB_HOST", "localhost"),
        db_port=int(_get("DB_PORT", "5432")),
        db_name=_get("DB_NAME", "ragdb"),
        db_user=_get("DB_USER", "postgres"),
        db_password=_get("DB_PASSWORD"),
        nvidia_api_key=_get("NVIDIA_API_KEY"),
        nvidia_base_url=_get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
        nvidia_llm_model=_get("NVIDIA_LLM_MODEL", "nvidia/nemotron-3.5-lightning-30b-a3b"),
        nvidia_vision_model=_get("NVIDIA_VISION_MODEL", "meta/llama-3.2-11b-vision-instruct"),
        embedding_model_name=_get("EMBEDDING_MODEL_NAME", "BAAI/bge-small-en-v1.5"),
        embedding_dim=int(_get("EMBEDDING_DIM", "384")),
        default_chunk_strategy=_get("DEFAULT_CHUNK_STRATEGY", "recursive"),
        default_excel_format=_get("DEFAULT_EXCEL_FORMAT", "markdown"),
        top_k=int(_get("TOP_K", "5")),
        similarity_threshold=float(_get("SIMILARITY_THRESHOLD", "0.35")),
        frontend_origin=_get("FRONTEND_ORIGIN", "http://localhost:5173"),
    )


settings = get_settings()
