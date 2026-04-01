from __future__ import annotations

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class SupabaseEmailClient:
    def __init__(self) -> None:
        self._project_url = settings.supabase_project_url.rstrip("/") if settings.supabase_project_url else None
        self._function_key = settings.supabase_edge_function_key
        self._function_name = settings.supabase_email_function_name

    @property
    def enabled(self) -> bool:
        return bool(self._project_url and self._function_key and self._function_name)

    async def send_standby_email(
        self,
        *,
        to_email: str,
        subject: str,
        body_text: str,
        metadata: dict | None = None,
    ) -> bool:
        if not self.enabled:
            logger.warning("standby_email_disabled", reason="missing_supabase_email_config")
            return False

        url = f"{self._project_url}/functions/v1/{self._function_name}"
        payload = {
            "to": to_email,
            "subject": subject,
            "text": body_text,
            "metadata": metadata or {},
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._function_key}",
            "apikey": self._function_key,
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                logger.info("standby_email_sent", to_email=to_email, function_name=self._function_name)
                return True
        except Exception as exc:
            logger.warning("standby_email_failed", to_email=to_email, error=str(exc))
            return False


def build_supabase_email_client() -> SupabaseEmailClient:
    return SupabaseEmailClient()
