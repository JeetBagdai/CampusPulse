"""Telegram bot notifier (free). Uses long polling, so no public URL is needed.

Staff link their chat to a role by opening t.me/<bot>?start=<role> and then pick
their language (English / Hindi / Kannada), changeable with /language. Anyone
else who messages the bot is treated as a student and can send photo reports
with the caption "REPORT <location>".
"""
import asyncio
import json
import logging
import os

import httpx

from ..config import DATA_DIR, TELEGRAM_BOT_TOKEN
from .base import Notifier

log = logging.getLogger("campuspulse.telegram")
ROLES = ("electrician", "plumber", "housekeeping", "estate_manager")
# short deep-link names: t.me/<bot>?start=electrical
ALIASES = {"electrical": "electrician", "water": "plumber", "waste": "housekeeping", "estate": "estate_manager"}
TITLES = {"electrician": "Electrical In-charge", "plumber": "Water & Plumbing In-charge",
          "housekeeping": "Housekeeping & Waste In-charge", "estate_manager": "Estate Manager"}
LANGS = [("en", "English"), ("hi", "हिन्दी"), ("kn", "ಕನ್ನಡ")]
CHATS_FILE = DATA_DIR / "telegram_chats.json"  # roles + language choices (gitignored)


class TelegramBot(Notifier):
    channel = "telegram"

    def __init__(self):
        self.api = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
        # hosted disks reset on deploy, so role links can also come from the TELEGRAM_CHATS secret
        raw = (CHATS_FILE.read_text() if CHATS_FILE.exists() else os.getenv("TELEGRAM_CHATS", "")).strip().strip("'\"")
        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            log.warning("TELEGRAM_CHATS is not valid JSON; starting with no linked roles")
            data = {}
        if "roles" not in data:  # older flat {role: chat_id} format
            data = {"roles": data, "langs": {}}
        self.chats: dict[str, int] = data["roles"]
        self.langs: dict[str, str] = data["langs"]  # chat_id (str) -> en|hi|kn
        self.username = None

    def configured(self) -> bool:
        return bool(TELEGRAM_BOT_TOKEN)

    def address(self, role: str) -> str:
        chat = self.chats.get(role)
        return f"tg:{chat}" if chat else ""

    def roles_for_address(self, address: str) -> list[str]:
        return self.roles_for(int(address[3:])) if address.startswith("tg:") else []

    def roles_for(self, chat_id: int) -> list[str]:
        return [r for r, c in self.chats.items() if c == chat_id]

    def lang_for_role(self, role: str) -> str | None:
        chat = self.chats.get(role)
        return self.langs.get(str(chat)) if chat else None

    def _save(self):
        CHATS_FILE.write_text(json.dumps({"roles": self.chats, "langs": self.langs}, indent=1))

    async def send(self, phone, text, buttons=None):
        if not phone.startswith("tg:"):
            return False, "no Telegram chat linked for this role"
        body = {"chat_id": int(phone[3:]), "text": text[:4000]}
        if buttons:
            body["reply_markup"] = {"inline_keyboard": [[{"text": t, "callback_data": bid} for bid, t in buttons[:3]]]}
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(f"{self.api}/sendMessage", json=body)
        return (True, "sent") if r.status_code == 200 else (False, r.json().get("description", f"HTTP {r.status_code}"))

    async def fetch_media(self, file_id: str) -> bytes | None:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get(f"{self.api}/getFile", params={"file_id": file_id})
            if r.status_code != 200:
                return None
            path = r.json()["result"]["file_path"]
            data = await c.get(f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{path}")
            return data.content if data.status_code == 200 else None

    async def _reply(self, chat_id: int, text: str, buttons=None):
        await self.send(f"tg:{chat_id}", text, buttons)

    async def _ask_language(self, chat_id: int, intro: str = ""):
        await self._reply(chat_id, (intro + "\n\n" if intro else "") + "Choose your language / भाषा चुनें / ಭಾಷೆ ಆಯ್ಕೆಮಾಡಿ:",
                          [(f"LANG:{code}", label) for code, label in LANGS])

    async def _handle(self, engine, upd: dict):
        if "callback_query" in upd:
            cq = upd["callback_query"]
            chat_id = cq["message"]["chat"]["id"]
            data = cq.get("data", "")
            async with httpx.AsyncClient(timeout=10) as c:
                await c.post(f"{self.api}/answerCallbackQuery", json={"callback_query_id": cq["id"]})
            if data.startswith("LANG:"):
                from ..genai.workorders import t
                code = data[5:]
                self.langs[str(chat_id)] = code
                self._save()
                await self._reply(chat_id, t("lang_set", code))
                return
            await engine.incoming(f"tg:{chat_id}", data, data, None, channel=self.channel)
            return
        msg = upd.get("message") or {}
        chat_id = msg.get("chat", {}).get("id")
        if not chat_id:
            return
        text = msg.get("text") or msg.get("caption") or ""
        if text.startswith("/language"):
            await self._ask_language(chat_id)
            return
        if text.startswith("/start"):
            arg = text.split(maxsplit=1)[1].strip().lower() if " " in text else ""
            arg = ALIASES.get(arg, arg)
            picked = list(ROLES) if arg == "all" else [arg] if arg in ROLES else []
            if picked:
                for r in picked:
                    self.chats[r] = chat_id
                self._save()
                await self._ask_language(chat_id, "You are now: " + ", ".join(TITLES[r] for r in picked) +
                                         ".\nCampusPulse work orders for you will arrive here. Tap Noted when you "
                                         "start and Done when it is fixed.")
            else:
                await self._reply(chat_id, "CampusPulse campus bot.\nStaff: open the role link you were given "
                                           "(or send /start electrical, water, waste or estate).\n"
                                           "Students: send a photo of a leak, overflowing bin or litter with the caption "
                                           "REPORT <location>, for example REPORT E-1WR.")
            return
        image = None
        if msg.get("photo"):
            image = await self.fetch_media(msg["photo"][-1]["file_id"])
        await engine.incoming(f"tg:{chat_id}", text, None, image, channel=self.channel)

    async def poll(self, engine):
        """Long-poll Telegram for updates and feed them to the engine."""
        offset = 0
        async with httpx.AsyncClient(timeout=40) as c:
            await c.post(f"{self.api}/deleteWebhook")
            me = (await c.get(f"{self.api}/getMe")).json()
            self.username = me.get("result", {}).get("username")
            await c.post(f"{self.api}/setMyCommands", json={"commands": [
                {"command": "language", "description": "Change language / भाषा / ಭಾಷೆ"},
                {"command": "start", "description": "How to use this bot"}]})
        while True:
            try:
                async with httpx.AsyncClient(timeout=40) as c:
                    r = await c.get(f"{self.api}/getUpdates", params={"timeout": 25, "offset": offset})
                for upd in r.json().get("result", []):
                    offset = upd["update_id"] + 1
                    try:
                        await self._handle(engine, upd)
                    except Exception:  # noqa: BLE001
                        log.exception("telegram update failed")
            except Exception:  # noqa: BLE001
                log.exception("telegram poll error")
                await asyncio.sleep(3)
