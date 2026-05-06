"""Kanitli cevap AI2 cagrisi icin izole process worker'i."""

import os


def evidence_ai_chat_worker(queue, messages: list[dict], max_tokens: int, timeout_seconds: int):
    try:
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dokuman_asistani.settings")
        import django

        django.setup()
        from django.conf import settings
        from dokuman.ai2.llm import chat

        settings.YEREL_MODEL_ETKIN = False
        queue.put(
            {
                "ok": True,
                "value": chat(
                    messages,
                    max_tokens=max_tokens,
                    timeout_seconds=timeout_seconds,
                    max_attempts_per_url=1,
                ),
            }
        )
    except Exception as exc:
        queue.put({"ok": False, "error_type": type(exc).__name__, "error": str(exc)})
