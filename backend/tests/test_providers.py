import inspect

import pytest

from app.providers import BrokerProvider, MarketDataProvider


def test_provider_contracts_are_abstract():
    assert inspect.isabstract(MarketDataProvider)
    assert inspect.isabstract(BrokerProvider)

    with pytest.raises(TypeError):
        MarketDataProvider()

    with pytest.raises(TypeError):
        BrokerProvider()

