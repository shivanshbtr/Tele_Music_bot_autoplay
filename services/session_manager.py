"""
Session Manager — in-memory store for per-user sessions.
In production, swap the dict for Redis or a database.
"""

import logging
from typing import Optional, Dict
from models import UserSession

logger = logging.getLogger(__name__)

# Global session store: {user_id: UserSession}
_sessions: Dict[int, UserSession] = {}


class SessionManager:
    """Thread-safe (asyncio-safe) in-memory session store."""

    def get(self, user_id: int, username: str = "") -> UserSession:
        """Return existing session or create a new one."""
        if user_id not in _sessions:
            _sessions[user_id] = UserSession(user_id=user_id, username=username)
            logger.info(f"New session created for user {user_id} ({username})")
        return _sessions[user_id]

    def delete(self, user_id: int) -> None:
        _sessions.pop(user_id, None)

    def all_sessions(self) -> list:
        return list(_sessions.values())

    def active_count(self) -> int:
        return len(_sessions)


# Singleton instance
session_manager = SessionManager()
