"""WhatsApp via Meta's Cloud API (Graph API)."""
import hashlib
import hmac

import httpx

from ..config import META
from .base import Notifier


class MetaWhatsApp(Notifier):
    channel = "whatsapp-meta"

    def __init__(self):
        self.base = f"https://graph.facebook.com/{META['graph_version']}"
        self.headers = {"Authorization": f"Bearer {META['token']}"}

    def configured(self) -> bool:
        return bool(META["token"] and META["phone_number_id"])

    async def send(self, phone, text, buttons=None):
        to = phone.lstrip("+")
        if buttons:
            payload = {"messaging_product": "whatsapp", "to": to, "type": "interactive",
                       "interactive": {"type": "button", "body": {"text": text[:1024]},
                                       "action": {"buttons": [{"type": "reply", "reply": {"id": bid, "title": title[:20]}}
                                                              for bid, title in buttons[:3]]}}}
        else:
            payload = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text[:4096]}}
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(f"{self.base}/{META['phone_number_id']}/messages", headers=self.headers, json=payload)
            if r.status_code != 200 and buttons and len(text) > 1024:
                return await self.send(phone, text, None)
        if r.status_code == 200:
            return True, "sent"
        try:
            err = r.json().get("error", {})
            return False, f"{err.get('code')}: {err.get('message', '')[:140]}"
        except ValueError:
            return False, f"HTTP {r.status_code}"

    async def fetch_media(self, media_id: str) -> bytes | None:
        async with httpx.AsyncClient(timeout=30) as c:
            meta = await c.get(f"{self.base}/{media_id}", headers=self.headers)
            if meta.status_code != 200:
                return None
            data = await c.get(meta.json()["url"], headers=self.headers)
            return data.content if data.status_code == 200 else None


def valid_signature(body: bytes, header: str | None) -> bool:
    """Checks X-Hub-Signature-256. If no app secret is configured, accept (dev mode)."""
    if not META["app_secret"]:
        return True
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(META["app_secret"].encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header[7:])


def parse_webhook(payload: dict) -> list[dict]:
    """Flattens a Meta webhook payload into [{from, text, button_id, media_id}]."""
    out = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            for m in change.get("value", {}).get("messages", []) or []:
                item = {"from": "+" + m.get("from", ""), "text": "", "button_id": None, "media_id": None}
                kind = m.get("type")
                if kind == "text":
                    item["text"] = m["text"]["body"]
                elif kind == "interactive":
                    reply = m["interactive"].get("button_reply") or m["interactive"].get("list_reply") or {}
                    item["button_id"], item["text"] = reply.get("id"), reply.get("title", "")
                elif kind == "button":
                    item["text"] = m["button"].get("text", "")
                elif kind == "image":
                    item["media_id"], item["text"] = m["image"]["id"], m["image"].get("caption", "")
                out.append(item)
    return out
