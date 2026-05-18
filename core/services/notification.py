"""Notification service for reviewer alerts."""

from __future__ import annotations

import logging
import os

import httpx
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


class NotificationService:
    """Sends reviewer notifications to Slack webhook when configured."""

    def __init__(self, webhook_url: str | None = None) -> None:
        load_dotenv()
        self._webhook_url = webhook_url if webhook_url is not None else os.getenv("SLACK_WEBHOOK_URL", "")

    def notify_reviewer(self, workflow_id: str, workflow_type: str, summary: str) -> bool:
        """Post reviewer notification; never raise on failure."""
        if not self._webhook_url:
            return False
        payload = {
            "text": "Workflow review requested",
            "workflow_id": workflow_id,
            "workflow_type": workflow_type,
            "summary": summary,
        }
        try:
            response = httpx.post(self._webhook_url, json=payload, timeout=30.0)
            response.raise_for_status()
            return True
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning(
                "notification_failed workflow_id=%s stage=%s error_type=%s",
                workflow_id,
                "notification",
                type(exc).__name__,
            )
            return False
