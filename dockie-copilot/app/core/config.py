from functools import lru_cache
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://dockie:dockie_secret@localhost:5432/dockie_copilot"
    sync_database_url: str = "postgresql://dockie:dockie_secret@localhost:5432/dockie_copilot"

    # App
    app_env: str = "development"
    log_level: str = "INFO"
    secret_key: str = "change-me"

    # Agent runtime
    adk_app_name: str = "dockie-copilot"
    adk_user_id: str = "local-user"
    adk_model: str = "gemini-3-flash-preview"
    adk_session_backend: str = "memory"
    adk_session_db_url: str | None = None
    agent_plan_cache_ttl_seconds: int = 120
    agent_audit_log_enabled: bool = True
    agent_audit_log_path: str = "runtime/agent_audit/agent_runs.jsonl"

    # External providers
    google_api_key: str | None = None
    openai_api_key: str | None = None
    aisstream_api_key: str | None = None
    aisstream_ws_url: str = "wss://stream.aisstream.io/v0/stream"
    aisstream_capture_window_seconds: int = 12
    aisstream_max_messages: int = 200
    aisstream_message_timeout_seconds: int = 4
    aisstream_max_tracked_mmsis: int = 50
    aisstream_capture_snapshot_path: str = "runtime/aisstream/latest_capture.json"
    source_http_timeout_seconds: int = 15
    source_http_user_agent: str = "DockieCopilot/0.1 (+schedule refresh)"
    source_fetch_debug: bool = False
    sallaum_schedule_url: str | None = None
    grimaldi_schedule_url: str | None = None
    nigerian_ports_url: str | None = None
    fake_web_registry_path: str = "../fake-websites/sources.json"
    fake_web_enabled: bool = True
    fake_web_fetch_ttl_seconds: int = 300
    fake_web_max_results: int = 5
    fake_web_max_sources_per_query: int = 4
    fake_web_max_parallel_fetches: int = 3
    knowledge_vector_enabled: bool = True
    knowledge_vector_backend: str = "array"
    knowledge_embedding_model: str = "text-embedding-3-small"
    knowledge_embedding_dimensions: int = 1536
    knowledge_embedding_version: str = "v1"
    knowledge_vector_top_k: int = 8

    # Source refresh controls
    source_fixtures_enabled: bool = True
    source_aisstream_enabled: bool = True
    source_sallaum_enabled: bool = True
    source_grimaldi_enabled: bool = True
    source_nigerian_ports_enabled: bool = True
    source_historical_ais_enabled: bool = True
    source_official_sanctions_enabled: bool = True

    # Cache
    cache_enabled: bool = True
    redis_url: str | None = None
    cache_prefix: str = "dockie"
    cache_list_shipments_ttl_seconds: int = 30
    cache_shipment_status_ttl_seconds: int = 30
    cache_shipment_history_ttl_seconds: int = 60
    cache_source_health_ttl_seconds: int = 60
    cache_singleflight_lock_ttl_seconds: int = 15
    cache_singleflight_wait_timeout_ms: int = 1500
    cache_singleflight_poll_interval_ms: int = 100

    # Standby worker
    standby_worker_poll_seconds: int = 10
    standby_worker_batch_size: int = 25
    standby_digest_send_hour_local: int = 8
    standby_default_cooldown_seconds: int = 600
    supabase_project_url: str | None = None
    supabase_edge_function_key: str | None = None
    supabase_email_function_name: str = "send-standby-email"
    supabase_jwks_url: str | None = None  # e.g. https://<project>.supabase.co/auth/v1/.well-known/jwks.json

    # Staleness thresholds (seconds)
    position_stale_after_seconds: int = 172800       # 2 days
    schedule_stale_after_seconds: int = 604800      # 7 days

    # Fixture paths
    resource_pack_path: str = "tests/fixtures/challenge_resource_pack.json"
    resource_pack_refresh_path: str = "tests/fixtures/challenge_resource_pack_refresh.json"
    malicious_payload_path: str = "tests/fixtures/challenge_malicious_payload.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()
