"""Sentry error tracking integration."""
import logging
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

logger = logging.getLogger(__name__)


def init_sentry(dsn: str, environment: str = "production", traces_sample_rate: float = 0.1):
    """Initialize Sentry SDK if DSN is provided."""
    if not dsn:
        return

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        integrations=[
            FastApiIntegration(),
            SqlalchemyIntegration(),
        ],
        traces_sample_rate=traces_sample_rate,
        send_default_pii=False,
    )
    logger.info("Sentry initialized (env=%s, sample_rate=%.0f%%)", environment, traces_sample_rate * 100)
