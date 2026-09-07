import logging

from app.config.settings import Settings


def configure_logging(settings: Settings) -> None:
    logging.basicConfig(
        level=settings.effective_log_level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        force=True,
    )

