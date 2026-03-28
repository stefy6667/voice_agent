"""
business_loader.py — Încarcă business_config.json și injectează în settings + FAQ

Cum funcționează:
  1. La pornirea aplicației, apelezi `load_business_config()`
  2. Loaderul citește business_config.json
  3. Suprascrie settings-urile relevante (nume, greeting, tone etc.)
  4. Generează automat FAQ-ul din secțiunea `faq` a config-ului
  5. Generează automat entries de sales din secțiunea `products`

Cum adaugi un client nou:
  1. Copiază business_config.json
  2. Completează câmpurile (business, products, faq, sales)
  3. Repornește serverul — gata!
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent.parent.parent / "business_config.json"
FAQ_GENERATED_PATH = Path(__file__).parent.parent.parent / "knowledge" / "business_faq_generated.json"


def load_business_config() -> dict[str, Any]:
    """Încarcă și returnează business_config.json. Returnează {} dacă lipsește."""
    if not CONFIG_PATH.exists():
        logger.info("[BusinessLoader] business_config.json nu există — folosesc valorile din .env")
        return {}

    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            config = json.load(f)
        logger.info("[BusinessLoader] ✅ business_config.json încărcat: %s", config.get("business", {}).get("name", "?"))
        return config
    except Exception as exc:
        logger.error("[BusinessLoader] ❌ Eroare la citirea business_config.json: %s", exc)
        return {}


def apply_to_settings(config: dict[str, Any]) -> None:
    """Suprascrie settings cu valorile din business_config.json."""
    if not config:
        return

    from app.config import settings

    business = config.get("business", {})
    personality = config.get("personality", {})
    handoff = config.get("handoff", {})

    # Business info
    if business.get("name"):
        settings.business_name = business["name"]
        logger.info("[BusinessLoader] business_name = %s", settings.business_name)

    if business.get("domain"):
        settings.business_domain = business["domain"]

    if business.get("agent_name"):
        settings.agent_name = business["agent_name"]

    if business.get("website_url"):
        settings.website_context_url = business["website_url"]
        if settings.website_context_mode == "faq_only":
            settings.website_context_mode = "on_demand"

    if business.get("language") == "ro":
        settings.twilio_default_language = "ro-RO"

    # Personality / tone
    if personality.get("tone"):
        settings.behavior_style_ro = personality["tone"]

    if personality.get("greeting_ro"):
        settings.greeting_ro = personality["greeting_ro"]

    if personality.get("greeting_en"):
        settings.greeting_en = personality["greeting_en"]

    # Handoff triggers — adăugăm la lista existentă din main.py
    # (main.py citește din settings dacă extindem, sau direct din config)
    # Stocăm în settings ca string CSV pentru acces ușor
    triggers = handoff.get("triggers", [])
    if triggers:
        settings.handoff_triggers_extra = ",".join(triggers)  # type: ignore[attr-defined]

    if handoff.get("message_ro"):
        settings.handoff_message_ro = handoff["message_ro"]  # type: ignore[attr-defined]

    logger.info("[BusinessLoader] ✅ Settings actualizate din business_config.json")


def generate_faq_from_config(config: dict[str, Any]) -> None:
    """
    Generează knowledge/business_faq_generated.json din secțiunile
    `faq`, `products` și `sales` ale config-ului.
    """
    if not config:
        return

    business = config.get("business", {})
    business_name = business.get("name", "compania noastră")
    agent_name = business.get("agent_name", "Ana")
    items: list[dict[str, Any]] = []

    # --- FAQ entries ---
    for i, entry in enumerate(config.get("faq", [])):
        q = entry.get("question", "")
        a = entry.get("answer", "")
        if not q or not a:
            continue
        items.append({
            "id": f"biz_faq_{i}",
            "language": "ro",
            "question": q,
            "answer": a,
            "source": "business_config_faq",
        })

    # --- Products → FAQ entries ---
    for i, product in enumerate(config.get("products", [])):
        name = product.get("name", "")
        desc = product.get("description", "")
        price = product.get("price", "")
        target = product.get("target_customer", "")

        if name and desc:
            items.append({
                "id": f"biz_product_{i}",
                "language": "ro",
                "question": f"Ce vindeți? / Ce oferiți? / Ce face {name}?",
                "answer": f"{name}: {desc}" + (f" Preț: {price}." if price else "") + (f" Ideal pentru: {target}." if target else ""),
                "source": "business_config_product",
            })

        if price:
            items.append({
                "id": f"biz_price_{i}",
                "language": "ro",
                "question": f"Cât costă {name}? / Care e prețul?",
                "answer": f"Prețul pentru {name} este {price}.",
                "source": "business_config_pricing",
            })

    # --- Sales objections ---
    sales = config.get("sales", {})
    objections = sales.get("objection_handling", {})
    for key, response in objections.items():
        items.append({
            "id": f"biz_objection_{key}",
            "language": "ro",
            "question": key.replace("_", " "),
            "answer": response,
            "source": "business_config_sales",
        })

    # CTA
    cta = sales.get("call_to_action", "")
    if cta:
        items.append({
            "id": "biz_cta",
            "language": "ro",
            "question": "Cum pot afla mai multe? / Vreau un demo",
            "answer": cta,
            "source": "business_config_sales",
        })

    # --- After hours ---
    schedule = config.get("schedule", {})
    after_hours = schedule.get("after_hours_message_ro", "")
    hours = schedule.get("working_hours", "")
    if hours:
        items.append({
            "id": "biz_schedule",
            "language": "ro",
            "question": "Când sunteți disponibili? / Program",
            "answer": f"Suntem disponibili {hours}." + (f" {after_hours}" if after_hours else ""),
            "source": "business_config_schedule",
        })

    if not items:
        logger.info("[BusinessLoader] Niciun item FAQ generat din business_config.json")
        return

    # Scrie fișierul generat
    FAQ_GENERATED_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(FAQ_GENERATED_PATH, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

    logger.info("[BusinessLoader] ✅ %d FAQ entries generate în %s", len(items), FAQ_GENERATED_PATH)


def init_business(reload_kb: bool = True) -> dict[str, Any]:
    """
    Funcția principală — apeleaz-o o dată la startup în main.py:

        from app.services.business_loader import init_business
        init_business()

    Returnează config-ul încărcat (util pentru debugging).
    """
    config = load_business_config()
    if not config:
        return {}

    apply_to_settings(config)
    generate_faq_from_config(config)

    if reload_kb:
        try:
            from app.main import kb
            kb.reload()
            logger.info("[BusinessLoader] ✅ Knowledge base reîncărcată cu FAQ din business_config")
        except Exception as exc:
            logger.warning("[BusinessLoader] KB reload eșuat (normal la primul start): %s", exc)

    return config
