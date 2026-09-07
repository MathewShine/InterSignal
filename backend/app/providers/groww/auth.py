from __future__ import annotations

from contextlib import redirect_stdout
from dataclasses import dataclass
from io import StringIO
from typing import Any

from app.config.settings import Settings
from app.providers.groww.exceptions import (
    GrowwAuthenticationError,
    GrowwProviderNotConfiguredError,
)


@dataclass(frozen=True, slots=True, repr=False)
class GrowwCredentials:
    totp_token: str
    totp_secret: str

    @classmethod
    def from_settings(cls, settings: Settings) -> "GrowwCredentials | None":
        if not settings.groww_configured:
            return None
        return cls(
            totp_token=settings.groww_totp_token or "",
            totp_secret=settings.groww_totp_secret or "",
        )


class GrowwAuthService:
    def __init__(
        self,
        *,
        credentials: GrowwCredentials | None,
        groww_api_cls: type | None = None,
        totp_factory: type | None = None,
    ) -> None:
        self.credentials = credentials
        self._groww_api_cls = groww_api_cls
        self._totp_factory = totp_factory
        self._client: Any | None = None

    @property
    def is_configured(self) -> bool:
        return self.credentials is not None

    def get_client(self, *, refresh: bool = False) -> Any:
        if not self.credentials:
            raise GrowwProviderNotConfiguredError()
        if self._client is not None and not refresh:
            return self._client

        try:
            groww_api_cls = self._resolve_groww_api_cls()
            totp_code = self._build_totp_code(self.credentials.totp_secret)
            with redirect_stdout(StringIO()):
                token_response = groww_api_cls.get_access_token(
                    api_key=self.credentials.totp_token,
                    totp=totp_code,
                )
                access_token = self._extract_access_token(token_response)
                self._client = groww_api_cls(access_token)
        except GrowwProviderNotConfiguredError:
            raise
        except Exception as exc:
            raise GrowwAuthenticationError() from exc

        return self._client

    def _resolve_groww_api_cls(self) -> type:
        if self._groww_api_cls is not None:
            return self._groww_api_cls

        from growwapi import GrowwAPI

        return GrowwAPI

    def _build_totp_code(self, secret: str) -> str:
        if self._totp_factory is None:
            import pyotp

            totp = pyotp.TOTP(secret)
        else:
            totp = self._totp_factory(secret)
        return str(totp.now())

    def _extract_access_token(self, token_response: Any) -> str:
        if isinstance(token_response, str) and token_response:
            return token_response

        if isinstance(token_response, dict):
            token = (
                token_response.get("token")
                or token_response.get("access_token")
                or token_response.get("accessToken")
            )
            if isinstance(token, str) and token:
                return token

        raise GrowwAuthenticationError()
