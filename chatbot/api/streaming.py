"""
SSE Streaming Implementation

Provides Server-Sent Events (SSE) for real-time progress updates during analysis.
"""

import json
import asyncio
from typing import AsyncGenerator, Dict, Any
from datetime import datetime


class SSEStream:
    """Server-Sent Events stream manager."""

    @staticmethod
    def format_sse(event: str, data: Dict[str, Any]) -> str:
        """
        Format data as SSE message.

        Args:
            event: Event type (progress, patterns_detected, threat_scores, complete, error)
            data: Event data

        Returns:
            Formatted SSE message
        """
        return f"event: {event}\ndata: {json.dumps(data)}\n\n"

    @staticmethod
    async def send_progress(
        stage: str,
        progress: int,
        message: str,
        eta_seconds: int = None,
        patterns_active: list = None
    ) -> str:
        """
        Send progress update event.

        Args:
            stage: Current stage (parsing, mitre, rapids, ai_ml, validation)
            progress: Progress percentage (0-100)
            message: Status message for user
            eta_seconds: Estimated time remaining
            patterns_active: List of active pattern IDs

        Returns:
            Formatted SSE message
        """
        data = {
            "stage": stage,
            "progress": progress,
            "message": message,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }

        if eta_seconds is not None:
            data["eta_seconds"] = eta_seconds

        if patterns_active:
            data["patterns_active"] = patterns_active

        return SSEStream.format_sse("progress", data)

    @staticmethod
    async def send_patterns_detected(patterns: list) -> str:
        """
        Send pattern detection event.

        Args:
            patterns: List of pattern dicts with id, name, scope, trigger

        Returns:
            Formatted SSE message
        """
        return SSEStream.format_sse("patterns_detected", {"patterns": patterns})

    @staticmethod
    async def send_threat_scores(scores_by_pattern: Dict[str, Dict]) -> str:
        """
        Send threat scores grouped by pattern.

        Args:
            scores_by_pattern: Dict mapping pattern_id to threat scores

        Returns:
            Formatted SSE message
        """
        return SSEStream.format_sse("threat_scores", scores_by_pattern)

    @staticmethod
    async def send_attack_path(path_data: Dict[str, Any]) -> str:
        """
        Send attack path discovery event.

        Args:
            path_data: Attack path with id, path, techniques

        Returns:
            Formatted SSE message
        """
        return SSEStream.format_sse("attack_path", path_data)

    @staticmethod
    async def send_complete(result: Dict[str, Any]) -> str:
        """
        Send analysis complete event.

        Args:
            result: Complete analysis result

        Returns:
            Formatted SSE message
        """
        return SSEStream.format_sse("complete", result)

    @staticmethod
    async def send_error(error_message: str, detail: str = None) -> str:
        """
        Send error event.

        Args:
            error_message: Error summary
            detail: Detailed error information

        Returns:
            Formatted SSE message
        """
        data = {"message": error_message}
        if detail:
            data["detail"] = detail

        return SSEStream.format_sse("error", data)


class ProgressTracker:
    """
    Track analysis progress and emit SSE events.

    Progress stages:
    - parsing: 0-10%
    - mitre: 10-20%
    - rapids: 20-60%
    - ai_ml: 60-80% (if applicable)
    - validation: 80-100%
    """

    STAGE_PROGRESS = {
        "parsing":    (0,  5),
        "rapids":     (5,  55),
        "ai_ml":      (55, 80),
        "validation": (80, 100),
    }

    def __init__(self, has_ai_ml: bool = False):
        """
        Initialize progress tracker.

        Args:
            has_ai_ml: Whether AI/ML pattern is active
        """
        self.has_ai_ml = has_ai_ml
        self.current_stage = "parsing"
        self.start_time = datetime.utcnow()

    def get_progress(self, stage: str, stage_percent: float = 0.5) -> int:
        """
        Calculate overall progress percentage.

        Args:
            stage: Current stage name
            stage_percent: Progress within stage (0.0-1.0)

        Returns:
            Overall progress (0-100)
        """
        if stage not in self.STAGE_PROGRESS:
            return 0

        start, end = self.STAGE_PROGRESS[stage]

        # If AI/ML not applicable, validation starts right after rapids
        if not self.has_ai_ml and stage == "validation":
            start = 55
            end = 100

        return int(start + (end - start) * stage_percent)

    def get_eta(self, progress: int) -> int:
        """
        Estimate time remaining in seconds.

        Args:
            progress: Current progress (0-100)

        Returns:
            Estimated seconds remaining
        """
        if progress <= 0:
            return 120  # Default 2 minutes

        elapsed = (datetime.utcnow() - self.start_time).total_seconds()
        total_estimated = elapsed / (progress / 100.0)
        remaining = total_estimated - elapsed

        return max(0, int(remaining))
