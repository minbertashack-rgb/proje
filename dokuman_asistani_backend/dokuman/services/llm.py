"""
Geriye donuk uyumluluk icin ince yonlendirme katmani.
Ana LLM akisi dokuman.ai2.llm icinde tutulur.
"""

from dokuman.ai2.llm import chat, dusunce_etiketlerini_temizle, llm_tamamla, yerel_modeli_al

__all__ = [
    "chat",
    "dusunce_etiketlerini_temizle",
    "llm_tamamla",
    "yerel_modeli_al",
]
