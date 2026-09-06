from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILES = (
    str(_REPO_ROOT / ".env"),
    ".env",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_provider: str = "NVIDIA"
    llm_api_key: str = ""
    llm_base_url: str = "https://integrate.api.nvidia.com/v1"
    llm_model: str = "meta/llama-3.1-8b-instruct"

    data_dir: Path = Path("./data")
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    # None = let ONNX Runtime pick; pinned to 1 by the eval/test harness for
    # reproducibility (multi-threaded reductions are not bit-exact run to run,
    # which can flip near-tied ANN ranks on a tiny corpus).
    embedding_threads: int | None = None

    public_chat_only: bool = False
    owner_secret: str = ""
    github_token: str = ""

    host: str = "0.0.0.0"
    port: int = 7860
    static_dir: Path | None = None

    # CORS: comma-separated origins, or "*" for all (never combined with credentials)
    allowed_origins: str = "*"

    # Retrieval: hybrid dense + BM25 fusion, cross-encoder rerank, relevance gate
    rerank_enabled: bool = True
    rerank_model: str = "Xenova/ms-marco-MiniLM-L-6-v2"
    rerank_candidate_k: int = 30
    rerank_top_k: int = 8
    relevance_gate_score: float = -2.0
    query_rewrite_enabled: bool = True

    # Rate limiting: in-process token bucket, no external store
    rate_limit_enabled: bool = True
    rate_limit_per_minute: float = 20.0
    rate_limit_burst: float = 10.0
    agent_daily_chat_limit: int = 300

    # Observability
    json_logs: bool = True

    def resolve_base_url(self) -> str:
        provider = self.llm_provider.upper()
        if self.llm_base_url:
            return self.llm_base_url.rstrip("/")
        defaults = {
            "NVIDIA": "https://integrate.api.nvidia.com/v1",
            "GROQ": "https://api.groq.com/openai/v1",
            "OLLAMA": "http://127.0.0.1:11434/v1",
            "OPENAI_COMPAT": "https://api.openai.com/v1",
        }
        return defaults.get(provider, defaults["NVIDIA"])

    @property
    def agents_dir(self) -> Path:
        path = self.data_dir / "agents"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings
