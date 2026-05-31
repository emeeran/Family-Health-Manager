"""AI service with multi-provider failover.

This module is a thin re-export shim. All implementation lives in
the ``app.services.ai`` package.  Keeping this file ensures that
``from app.services.ai_service import AIService`` continues to work
for every caller and test patch path.
"""
from app.core.config import get_settings
from app.services.ai import AIService

settings = get_settings()

__all__ = ["AIService", "settings"]
