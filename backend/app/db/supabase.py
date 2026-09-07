from typing import Any

from app.config.settings import Settings, get_settings


class SupabaseHealthStatus:
    def __init__(self, status: str, configured: bool, detail: str) -> None:
        self.status = status
        self.configured = configured
        self.detail = detail


class SupabaseClientFactory:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client: Any | None = None

    @property
    def is_configured(self) -> bool:
        return self.settings.supabase_configured

    def get_client(self) -> Any | None:
        if not self.is_configured:
            return None

        if self._client is None:
            from supabase import create_client

            key = (
                self.settings.supabase_service_role_key
                or self.settings.supabase_anon_key
            )
            self._client = create_client(self.settings.supabase_url, key)

        return self._client

    def check_connection(self) -> SupabaseHealthStatus:
        if not self.is_configured:
            return SupabaseHealthStatus(
                status="not_configured",
                configured=False,
                detail="Supabase credentials are not configured.",
            )

        try:
            client = self.get_client()
            client.table("instruments").select("id").limit(1).execute()
        except Exception:
            return SupabaseHealthStatus(
                status="unavailable",
                configured=True,
                detail="Supabase credentials are present, but the database check failed.",
            )

        return SupabaseHealthStatus(
            status="ok",
            configured=True,
            detail="Supabase database check succeeded.",
        )
