"""
business_loader.py — fix limba: nu mai forteaza engleza, FAQ bilingv
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
    if not CONFIG_PATH.exists():
        logger.info("[BusinessLoader] business_config.json nu exista — folosesc .env")
        return {}
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            config = json.load(f)
        logger.info("[BusinessLoader] Incarcat: %s", config.get("business", {}).get("name", "?"))
        return config
    except Exception as exc:
        logger.error("[BusinessLoader] Eroare: %s", exc)
        return {}


def apply_to_settings(config: dict[str, Any]) -> None:
    if not config:
        return

    from app.config import settings

    business = config.get("business", {})
    personality = config.get("personality", {})
    handoff = config.get("handoff", {})

    if business.get("name"):
        settings.business_name = business["name"]
    if business.get("domain"):
        settings.business_domain = business["domain"]
    if business.get("agent_name"):
        settings.agent_name = business["agent_name"]
    if business.get("website_url"):
        settings.website_context_url = business["website_url"]
        if settings.website_context_mode == "faq_only":
            settings.website_context_mode = "on_demand"

    # FIX: nu suprascrie twilio_default_language daca e deja setat in .env
    # Lasa .env sa controleze limba default — business_config nu o mai atinge
    # if business.get("language") == "ro":
    #     settings.twilio_default_language = "ro-RO"  # <-- COMENTAT, cauza problemei

    if personality.get("tone"):
        settings.behavior_style_ro = personality["tone"]
    if personality.get("greeting_ro"):
        settings.greeting_ro = personality["greeting_ro"]
    if personality.get("greeting_en"):
        settings.greeting_en = personality["greeting_en"]

    triggers = handoff.get("triggers", [])
    if triggers:
        settings.handoff_triggers_extra = ",".join(triggers)  # type: ignore[attr-defined]
    if handoff.get("message_ro"):
        settings.handoff_message_ro = handoff["message_ro"]  # type: ignore[attr-defined]

    logger.info("[BusinessLoader] Settings actualizate OK")


def generate_faq_from_config(config: dict[str, Any]) -> None:
    if not config:
        return

    business = config.get("business", {})
    items: list[dict[str, Any]] = []

    # FAQ entries — adauga AMBELE limbi pentru fiecare intrebare
    # Asta previne knowledge base sa returneze match in limba gresita
    for i, entry in enumerate(config.get("faq", [])):
        q = entry.get("question", "")
        a = entry.get("answer", "")
        if not q or not a:
            continue
        # Versiunea romana
        items.append({
            "id": f"biz_faq_{i}_ro",
            "language": "ro",
            "question": q,
            "answer": a,
            "source": "business_config_faq",
        })
        # Nu generam versiune engleza automata pentru FAQ custom
        # Clientul poate adauga manual daca vrea bilingv

    # Produse
    for i, product in enumerate(config.get("products", [])):
        name = product.get("name", "")
        desc = product.get("description", "")
        price = product.get("price", "")
        target = product.get("target_customer", "")

        if name and desc:
            answer_ro = f"{name}: {desc}"
            if price:
                answer_ro += f" Pret: {price}."
            if target:
                answer_ro += f" Ideal pentru: {target}."

            items.append({
                "id": f"biz_product_{i}_ro",
                "language": "ro",
                "question": f"Ce vindeti? / Ce oferiti? / Ce face {name}?",
                "answer": answer_ro,
                "source": "business_config_product",
            })
            # Varianta engleza
            answer_en = f"{name}: {desc}"
            if price:
                answer_en += f" Price: {price}."
            if target:
                answer_en += f" Ideal for: {target}."
            items.append({
                "id": f"biz_product_{i}_en",
                "language": "en",
                "question": f"What do you sell? / What does {name} do?",
                "answer": answer_en,
                "source": "business_config_product",
            })

        if price:
            items.append({
                "id": f"biz_price_{i}_ro",
                "language": "ro",
                "question": f"Cat costa {name}? / Care e pretul?",
                "answer": f"Pretul pentru {name} este {price}.",
                "source": "business_config_pricing",
            })
            items.append({
                "id": f"biz_price_{i}_en",
                "language": "en",
                "question": f"How much does {name} cost? / What is the price?",
                "answer": f"The price for {name} is {price}.",
                "source": "business_config_pricing",
            })

    # Obiectii vanzari
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

    cta = sales.get("call_to_action", "")
    if cta:
        items.append({
            "id": "biz_cta_ro",
            "language": "ro",
            "question": "Cum pot afla mai multe? / Vreau un demo",
            "answer": cta,
            "source": "business_config_sales",
        })

    # Program
    schedule = config.get("schedule", {})
    after_hours = schedule.get("after_hours_message_ro", "")
    hours = schedule.get("working_hours", "")
    if hours:
        items.append({
            "id": "biz_schedule_ro",
            "language": "ro",
            "question": "Cand sunteti disponibili? / Program",
            "answer": f"Suntem disponibili {hours}." + (f" {after_hours}" if after_hours else ""),
            "source": "business_config_schedule",
        })

    if not items:
        logger.info("[BusinessLoader] Niciun item FAQ generat")
        return

    FAQ_GENERATED_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(FAQ_GENERATED_PATH, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

    logger.info("[BusinessLoader] %d FAQ entries generate", len(items))


def init_business(reload_kb: bool = True) -> dict[str, Any]:
    config = load_business_config()
    if not config:
        return {}

    apply_to_settings(config)
    generate_faq_from_config(config)

    if reload_kb:
        try:
            from app.main import kb
            kb.reload()
            logger.info("[BusinessLoader] Knowledge base reincarcata")
        except Exception as exc:
            logger.warning("[BusinessLoader] KB reload esuat (normal la primul start): %s", exc)

    return config
