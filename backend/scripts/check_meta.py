"""Meta WhatsApp diagnostics: number status + test sends. Prints only status/errors, never secrets.
Run from backend/:  python scripts/check_meta.py [--text-only]"""
import asyncio
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import META, STAFF_PHONES  # noqa: E402
from app.notify.base import mask  # noqa: E402

BASE = f"https://graph.facebook.com/{META['graph_version']}"
H = {"Authorization": f"Bearer {META['token']}"}


async def main(text_only: bool):
    to = STAFF_PHONES["electrician"]
    print("recipient:", mask(to), "| digits:", len(to.lstrip("+")))
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(f"{BASE}/{META['phone_number_id']}", headers=H, params={
            "fields": "display_phone_number,verified_name,status,quality_rating,code_verification_status,platform_type"})
        print("number:", r.json())
        sends = [("free-form text", {"type": "text", "text": {"body": "✅ CampusPulse test: free-form message works."}})]
        if not text_only:
            sends.insert(0, ("hello_world template", {"type": "template",
                                                      "template": {"name": "hello_world", "language": {"code": "en_US"}}}))
        for label, body in sends:
            r = await c.post(f"{BASE}/{META['phone_number_id']}/messages", headers=H,
                             json={"messaging_product": "whatsapp", "to": to.lstrip("+"), **body})
            j = r.json()
            if r.status_code == 200:
                print(f"{label}: accepted, wa_id match={j['contacts'][0]['wa_id'] == to.lstrip('+')}, "
                      f"status={j['messages'][0].get('message_status')}")
            else:
                e = j.get("error", {})
                print(f"{label}: ERROR {e.get('code')} {e.get('message')} | {e.get('error_data', {}).get('details', '')}")


asyncio.run(main("--text-only" in sys.argv))
