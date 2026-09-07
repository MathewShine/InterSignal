import pytest

from app.providers.groww import (
    GrowwAuthService,
    GrowwAuthenticationError,
    GrowwCredentials,
    GrowwProviderNotConfiguredError,
)


class FakeTotp:
    def __init__(self, secret):
        self.secret = secret

    def now(self):
        return "123456"


class FakeGrowwAPI:
    access_token_response = "fixture-access-token"
    requested_api_key = None
    requested_totp = None
    constructed_token = None

    @staticmethod
    def get_access_token(api_key, totp=None, secret=None):
        FakeGrowwAPI.requested_api_key = api_key
        FakeGrowwAPI.requested_totp = totp
        return FakeGrowwAPI.access_token_response

    def __init__(self, token):
        FakeGrowwAPI.constructed_token = token


def test_groww_auth_requires_credentials():
    service = GrowwAuthService(
        credentials=None,
        groww_api_cls=FakeGrowwAPI,
        totp_factory=FakeTotp,
    )

    with pytest.raises(GrowwProviderNotConfiguredError):
        service.get_client()


def test_groww_auth_generates_totp_and_builds_client():
    FakeGrowwAPI.access_token_response = "fixture-access-token"
    service = GrowwAuthService(
        credentials=GrowwCredentials(
            totp_token="fixture-api-key",
            totp_secret="fixture-totp-seed",
        ),
        groww_api_cls=FakeGrowwAPI,
        totp_factory=FakeTotp,
    )

    client = service.get_client()

    assert isinstance(client, FakeGrowwAPI)
    assert FakeGrowwAPI.requested_api_key == "fixture-api-key"
    assert FakeGrowwAPI.requested_totp == "123456"
    assert FakeGrowwAPI.constructed_token == "fixture-access-token"


def test_groww_auth_accepts_sdk_token_dict_shape():
    FakeGrowwAPI.access_token_response = {"token": "dict-token"}
    service = GrowwAuthService(
        credentials=GrowwCredentials(
            totp_token="local-api-key",
            totp_secret="fixture-totp-seed",
        ),
        groww_api_cls=FakeGrowwAPI,
        totp_factory=FakeTotp,
    )

    service.get_client()

    assert FakeGrowwAPI.constructed_token == "dict-token"


def test_groww_auth_failure_message_is_sanitized():
    class FailingGrowwAPI(FakeGrowwAPI):
        @staticmethod
        def get_access_token(api_key, totp=None, secret=None):
            raise RuntimeError(f"bad key {api_key}")

    service = GrowwAuthService(
        credentials=GrowwCredentials(
            totp_token="fixture-api-key",
            totp_secret="fixture-totp-seed",
        ),
        groww_api_cls=FailingGrowwAPI,
        totp_factory=FakeTotp,
    )

    with pytest.raises(GrowwAuthenticationError) as exc_info:
        service.get_client()

    assert "fixture-api-key" not in str(exc_info.value)
    assert "fixture-totp-seed" not in str(exc_info.value)
