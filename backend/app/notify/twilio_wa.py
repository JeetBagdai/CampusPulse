"""WhatsApp via Twilio.

Sends a plain body first. If the sender requires Content templates (error 21654
"ContentSid Required"), it creates generic templates once via the Content API
(a text template and a 2-button quick-reply) and sends through those. Inside the
24-hour session window these don't need WhatsApp approval.
"""
import asyncio
import json

import httpx

from ..config import TWILIO
from .base import Notifier

CONTENT_URL = "https://content.twilio.com/v1/Content"
TEMPLATES = {
    "campuspulse_text_v1": {"language": "en", "variables": {"1": "message"},
                            "types": {"twilio/text": {"body": "{{1}}"}}},
    "campuspulse_buttons_v1": {"language": "en", "variables": {"1": "message", "2": "ACK:WO-1", "3": "DONE:WO-1"},
                               "types": {"twilio/quick-reply": {"body": "{{1}}", "actions": [
                                   {"title": "Noted", "id": "{{2}}"}, {"title": "Done", "id": "{{3}}"}]}}},
}


class TwilioWhatsApp(Notifier):
    channel = "whatsapp-twilio"

    def __init__(self):
        self.auth = (TWILIO["sid"], TWILIO["token"])
        self._sids: dict[str, str] = {}
        self.needs_content = bool(TWILIO["content_text"])

    def configured(self) -> bool:
        return bool(TWILIO["sid"] and TWILIO["token"] and TWILIO["from"])

    async def _content_sid(self, name: str) -> str:
        preset = TWILIO["content_buttons" if "buttons" in name else "content_text"]
        if preset:  # created by hand in the console (trial accounts can't use the Content API)
            return preset
        if name in self._sids:
            return self._sids[name]
        async with httpx.AsyncClient(timeout=20, auth=self.auth) as c:
            r = await c.get(CONTENT_URL, params={"PageSize": 100})
            r.raise_for_status()
            for item in r.json().get("contents", []):
                if item["friendly_name"] == name:
                    self._sids[name] = item["sid"]
                    return item["sid"]
            r = await c.post(CONTENT_URL, json={"friendly_name": name, **TEMPLATES[name]})
            r.raise_for_status()
            self._sids[name] = r.json()["sid"]
            return self._sids[name]

    def _create(self, **kw):
        from twilio.rest import Client
        return Client(*self.auth).messages.create(from_=TWILIO["from"], to=kw.pop("to"), **kw)

    async def send(self, phone, text, buttons=None):
        to = f"whatsapp:{phone}"
        try:
            if not self.needs_content:
                try:
                    msg = await asyncio.to_thread(self._create, to=to, body=text[:1600])
                    return True, msg.status
                except Exception as e:  # noqa: BLE001
                    if getattr(e, "code", None) != 21654:
                        raise
                    self.needs_content = True
            ids = [b[0] for b in buttons or [] if ":" in b[0]]
            if len(ids) == 2:
                sid = await self._content_sid("campuspulse_buttons_v1")
                # console-made template has fixed button ids ACK / DONE; the engine resolves the work order
                variables = ({"1": text[:1000]} if TWILIO["content_buttons"]
                             else {"1": text[:1000], "2": ids[0], "3": ids[1]})
            else:
                sid = await self._content_sid("campuspulse_text_v1")
                variables = {"1": text[:1500]}
            msg = await asyncio.to_thread(self._create, to=to, content_sid=sid,
                                          content_variables=json.dumps(variables, ensure_ascii=False))
            return True, msg.status
        except httpx.HTTPStatusError as e:
            return False, f"content API: {e.response.status_code} {e.response.text[:120]}"
        except Exception as e:  # noqa: BLE001
            return False, f"{getattr(e, 'code', '')} {str(getattr(e, 'msg', e))[:140]}"

    async def fetch_media(self, media_url: str) -> bytes | None:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
            r = await c.get(media_url, auth=self.auth)
            return r.content if r.status_code == 200 else None
