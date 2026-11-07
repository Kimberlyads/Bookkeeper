"""Stubs opcionais para testes quando dependências reais estão ausentes.

telegram e dotenv são verificados de forma independente. Se o pacote real
estiver instalado, ele é usado; o stub só entra quando falta a dependência.
"""

from __future__ import annotations

import sys
import types


def _ensure_telegram_stub() -> None:
    try:
        import telegram  # noqa: F401
        return
    except ImportError:
        pass

    telegram = types.ModuleType("telegram")

    class Update:
        pass

    class InlineKeyboardButton:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    class InlineKeyboardMarkup:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    telegram.Update = Update
    telegram.InlineKeyboardButton = InlineKeyboardButton
    telegram.InlineKeyboardMarkup = InlineKeyboardMarkup
    sys.modules["telegram"] = telegram

    ext = types.ModuleType("telegram.ext")

    class Application:
        pass

    class CallbackQueryHandler:
        def __init__(self, *args, **kwargs):
            pass

    class CommandHandler:
        def __init__(self, *args, **kwargs):
            pass

    class ContextTypes:
        class DEFAULT_TYPE:
            pass

    ext.Application = Application
    ext.CallbackQueryHandler = CallbackQueryHandler
    ext.CommandHandler = CommandHandler
    ext.ContextTypes = ContextTypes
    sys.modules["telegram.ext"] = ext
    telegram.ext = ext


def _ensure_dotenv_stub() -> None:
    try:
        import dotenv  # noqa: F401
        return
    except ImportError:
        pass

    dotenv = types.ModuleType("dotenv")

    def load_dotenv(*args, **kwargs):
        return False

    dotenv.load_dotenv = load_dotenv
    sys.modules["dotenv"] = dotenv


_ensure_telegram_stub()
_ensure_dotenv_stub()
