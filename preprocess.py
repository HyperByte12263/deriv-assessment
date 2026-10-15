"""PREPROCESSING: identify non-English / mixed-language tickets and produce English text.

LLM translation when a provider is configured; otherwise a small phrase glossary so that
downstream keyword rules and TF-IDF still see English terms. Original text is always kept.
"""
import json
import re

import llm_client
from vocab import LLM_STAGES

ENGLISH_HINTS = {"en", "en-us", "en-gb"}
COMMON_ENGLISH = {"the", "my", "i", "is", "and", "to", "for", "please", "why", "what", "can", "how", "not", "have"}

# Phrase-first glossary for the offline fallback (Malay and Hinglish support vocabulary).
GLOSSARY = [
    ("cut gaye", "were debited"), ("kata laluan", "password"), ("log masuk", "login"),
    ("complaint raise karu", "raise a complaint"), ("wait karna chahiye", "wait"),
    ("reflect nahi hua", "did not reflect"), ("disemak semula", "reviewed again"),
    ("mera", "my"), ("meri", "my"), ("mujhe", "I"), ("paise", "money"), ("paisa", "money"),
    ("nahi", "not"), ("kya", "should"), ("ya", "or"), ("se", "from"), ("pe", "on"), ("khata", "account"),
    ("saya", "I"), ("sudah", "already"), ("lulus", "passed"), ("pengesahan", "verification"),
    ("sebelum", "before"), ("ini", "this"), ("tetapi", "but"), ("sekarang", "now"),
    ("diminta", "requested"), ("dokumen", "documents"), ("tambahan", "additional"), ("lagi", "again"),
    ("kenapa", "why"), ("akaun", "account"), ("wang", "money"), ("pengeluaran", "withdrawal"),
    ("tidak", "not"), ("dan", "and"), ("disekat", "blocked"), ("digantung", "suspended"),
]


def needs_translation(ticket):
    hint = (ticket.get("language_hint") or "").strip().lower()
    if hint:
        return hint not in ENGLISH_HINTS
    words = re.findall(r"[a-z']+", (ticket["subject"] + " " + ticket["message"]).lower())
    return sum(w in COMMON_ENGLISH for w in words) / max(len(words), 1) < 0.15


def glossary_translate(text):
    out = text
    for src, dst in GLOSSARY:
        out = re.sub(rf"\b{re.escape(src)}\b", dst, out, flags=re.IGNORECASE)
    return out


SYSTEM = "You translate customer support tickets into plain English. Translate faithfully; do not add or remove facts."


def translate_batch(tickets, input_artifacts, output_artifact):
    """Return {ticket_id: (subject_en, message_en, method)} for tickets needing translation."""
    todo = [t for t in tickets if needs_translation(t)]
    if not todo:
        return {}
    payload = [{"ticket_id": t["ticket_id"], "language_hint": t.get("language_hint"),
                "subject": t["subject"], "message": t["message"]} for t in todo]
    prompt = (
        "Translate each ticket's subject and message into English.\n"
        'Return a JSON array of objects: {"ticket_id": str, "subject_en": str, "message_en": str}.\n'
        "Tickets:\n" + json.dumps(payload, ensure_ascii=False, indent=2)
    )
    stage = LLM_STAGES["translation"]
    if llm_client.provider() is None:
        llm_client.log_offline(stage, prompt, SYSTEM, input_artifacts, output_artifact)
        response = None
    else:
        response = llm_client.complete_json(prompt, SYSTEM, tag=stage,
                                            input_artifacts=input_artifacts, output_artifact=output_artifact)
    originals = {t["ticket_id"]: t for t in todo}
    by_id = {}
    if isinstance(response, list):
        for item in response:
            if not isinstance(item, dict) or str(item.get("ticket_id")) not in originals:
                continue
            orig = originals[str(item["ticket_id"])]
            # Models drift on key names; accept either, but reject an untranslated echo of the original.
            subj = item.get("subject_en") or item.get("subject")
            msg = item.get("message_en") or item.get("message")
            if isinstance(subj, str) and isinstance(msg, str) and msg.strip() and msg.strip() != orig["message"].strip():
                by_id[orig["ticket_id"]] = (subj, msg, "llm")
    for t in todo:  # any ticket the model missed falls back to the glossary
        by_id.setdefault(t["ticket_id"], (glossary_translate(t["subject"]), glossary_translate(t["message"]), "glossary"))
    return by_id


def preprocess(tickets, input_artifacts, output_artifact):
    translations = translate_batch(tickets, input_artifacts, output_artifact)
    out = []
    for t in tickets:
        tid = t["ticket_id"]
        lang = (t.get("language_hint") or "unknown").strip().lower()
        if tid in translations:
            subj, msg, method = translations[tid]
        else:
            subj, msg, method = t["subject"], t["message"], "none"
        out.append({
            "ticket_id": tid,
            "original_subject": t["subject"],
            "original_message": t["message"],
            "subject_for_processing": subj,
            "message_for_processing": msg,
            "original_language": lang,
            "translated": tid in translations,
            "translation_method": method,
        })
    return out
