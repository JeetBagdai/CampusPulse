from ..config import NOTIFIER
from .base import Notifier
from .meta_wa import MetaWhatsApp
from .telegram_bot import TelegramBot
from .twilio_wa import TwilioWhatsApp


def make_notifier() -> Notifier:
    """Real channel from NOTIFIER if configured, else console (in-app phone mock-up only)."""
    real = {"meta": MetaWhatsApp, "twilio": TwilioWhatsApp, "telegram": TelegramBot}.get(NOTIFIER)
    if real:
        n = real()
        if n.configured():
            return n
    return Notifier()
