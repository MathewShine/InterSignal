import asyncio
import zipfile
from pathlib import Path

from app.providers.historical import NSEFileProvider

FIXTURES = Path(__file__).parent / "fixtures"


def test_nse_file_provider_normalizes_local_zip_bhavcopy(tmp_path):
    zip_path = tmp_path / "nse_bhavcopy.zip"
    fixture = FIXTURES / "sample_nse_bhavcopy.csv"

    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.write(fixture, arcname="sample_nse_bhavcopy.csv")

    provider = NSEFileProvider(
        file_path=zip_path,
        file_format="daily_bhavcopy",
        source="synthetic_nse_fixture",
    )

    result = asyncio.run(provider.get_daily_candles())

    assert result.rows_read == 2
    assert result.errors == []
    assert result.records[0].trading_symbol == "ALPHA"
    assert result.records[0].source == "synthetic_nse_fixture"

