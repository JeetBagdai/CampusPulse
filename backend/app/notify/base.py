"""Notifier interface + the shared message feed shown in the UI's WhatsApp panel.

Every message (sent or received, real or console) lands in the feed, so the
demo still shows the conversation if the real WhatsApp channel is down.
"""
import itertools
import time
from collections import deque


def mask(phone: str) -> str:
    return phone[:3] + "•" * max(len(phone) - 7, 0) + phone[-4:] if phone else ""


class Feed:
    def __init__(self, maxlen: int = 200):
        self.items: deque = deque(maxlen=maxlen)
        self._ids = itertools.count(1)

    def add(self, direction: str, role: str, text: str, channel: str, status: str = "ok", **extra) -> dict:
        item = {"id": next(self._ids), "ts": time.time(), "dir": direction, "role": role, "text": text,
                "channel": channel, "status": status, **extra}
        self.items.append(item)
        return item

    def recent(self, n: int = 60) -> list[dict]:
        return list(self.items)[-n:]


class Notifier:
    channel = "console"

    def configured(self) -> bool:
        return True

    async def send(self, phone: str, text: str, buttons: list[tuple[str, str]] | None = None) -> tuple[bool, str]:
        """Returns (delivered, detail). `buttons` = [(id, title)] where the channel supports them."""
        return True, "console"

    async def fetch_media(self, media_ref: str) -> bytes | None:
        return None

    def address(self, role: str) -> str:
        """Where to send a role's messages (phone number by default)."""
        from ..config import STAFF_PHONES
        return STAFF_PHONES.get(role, "")

    def roles_for_address(self, address: str) -> list[str]:
        return []

    def lang_for_role(self, role: str) -> str | None:
        return None
