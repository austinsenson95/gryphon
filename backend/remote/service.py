"""Pairing, authorization, and lifecycle for a local remote session."""

from __future__ import annotations

import secrets
import socket
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from backend.remote.macos import MacRemoteAdapter


@dataclass
class RemoteSession:
    code: str
    expires_at: datetime
    token: str | None = None
    paired_at: datetime | None = None
    last_seen_at: datetime | None = None


class RemoteControlService:
    def __init__(self, adapter: MacRemoteAdapter | None = None, ttl_minutes: int = 30) -> None:
        self.adapter = adapter or MacRemoteAdapter()
        self.ttl_minutes = ttl_minutes
        self.session: RemoteSession | None = None
        self.device_name = socket.gethostname().split(".")[0] or "This Mac"
        self.lan_address = self._discover_lan_address()

    @staticmethod
    def _discover_lan_address() -> str | None:
        """Resolve the address macOS would use on the local network.

        Connecting a UDP socket selects a route but sends no traffic. This is
        more reliable on macOS than resolving the Bonjour hostname.
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("192.0.2.1", 9))
            address = sock.getsockname()[0]
            return address if address and not address.startswith("127.") else None
        except OSError:
            return None
        finally:
            sock.close()

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def _active(self) -> RemoteSession | None:
        if self.session and self.session.expires_at > self._now():
            return self.session
        self.session = None
        return None

    def start(self) -> dict:
        code = f"{secrets.randbelow(1_000_000):06d}"
        self.session = RemoteSession(
            code=code,
            expires_at=self._now() + timedelta(minutes=self.ttl_minutes),
        )
        return {**self.status(), "pairing_code": code}

    def pair(self, code: str) -> dict:
        session = self._active()
        if not session or not secrets.compare_digest(session.code, code.strip()):
            raise PermissionError("The pairing code is invalid or has expired.")
        if session.token is None:
            session.token = secrets.token_urlsafe(32)
            session.paired_at = self._now()
        session.last_seen_at = self._now()
        return {"token": session.token, **self.status()}

    def authenticate(self, token: str | None) -> RemoteSession:
        session = self._active()
        if not token or not session or not session.token or not secrets.compare_digest(session.token, token):
            raise PermissionError("This remote session is not paired or has expired.")
        session.last_seen_at = self._now()
        return session

    def stop(self) -> None:
        self.session = None

    def status(self) -> dict:
        session = self._active()
        permissions = self.adapter.permissions()
        return {
            "supported": self.adapter.supported,
            "device_name": self.device_name,
            "lan_address": self.lan_address,
            "state": "paired" if session and session.token else "pairing" if session else "idle",
            "expires_at": session.expires_at.isoformat() if session else None,
            "permissions": permissions,
            "ready": self.adapter.supported and all(permissions.values()),
        }
