from typing import Protocol

import httpx

from app.config import settings
from app.services.knowledge_base import KnowledgeMatch


class LLMProvider(Protocol):
    async def generate(
        self,
        user_text: str,
        language: str,
        kb_match: KnowledgeMatch | None,
        context: dict,
        skill_instruction: str | None = None,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> str:
        ...


class MockLLMProvider:
    @staticmethod
    def _already_answered_kb(history: list[dict[str, str]], kb_match: KnowledgeMatch | None) -> bool:
        if not kb_match:
            return False
        recent_assistant_turns = [turn["text"].lower() for turn in history[-4:] if turn["role"] == "assistant"]
        answer_prefix = kb_match.answer.lower()[:30]
        return any(answer_prefix in turn or kb_match.source.lower() in turn for turn in recent_assistant_turns)

    @staticmethod
    def _invoice_follow_up(language: str) -> str:
        if language == "ro":
            return (
                "Pot să te ajut mai concret cu factura. Spune-mi, te rog, dacă vrei retransmiterea pe email, "
                "schimbarea adresei de facturare sau verificarea ultimei plăți."
            )
        return (
            "I can help with the invoice in more detail. Please tell me if you want it resent by email, "
            "need to update the billing address, or want me to check the latest payment."
        )

    @staticmethod
    def _grounded_kb_reply(language: str, user_text: str, kb_match: KnowledgeMatch) -> str:
        source = kb_match.source.lower()
        if language == "ro":
            if "factura" in source:
                return (
                    "Da, te pot ajuta cu factura. Din informațiile pe care le am, factura se trimite pe email după confirmarea plății, "
                    "de obicei în maximum 24 de ore. Dacă vrei, putem vedea imediat dacă ai nevoie de retransmitere sau de schimbarea adresei de email."
                )
            if "comanda" in source or "livrare" in source:
                return (
                    "Sigur. Din informațiile pe care le am, livrarea durează de regulă între 1 și 3 zile lucrătoare. "
                    "Dacă vrei, spune-mi când ai plasat comanda și te ajut să estimăm mai exact."
                )
            return (
                f"Din informațiile pe care le am, răspunsul este acesta: {kb_match.answer} "
                "Dacă vrei, îl transformăm imediat într-un pas concret pentru situația ta."
            )

        if "pricing" in source:
            return (
                "Yes — the personalized AI agent bot is priced at 5000 dollars, "
                "and the ongoing maintenance and hosting fee is 25 dollars per month. "
                "If you want, I can also show you what that would look like for your business in a live demo."
            )
        if "demo" in source:
            return (
                "The demo is tailored to your business. "
                "I can simulate how the agent would greet your customer, qualify the request, answer naturally, and move the conversation toward booking, follow-up, or closing."
            )
        if "ai_agent" in source or "value" in source:
            return (
                "We sell custom AI agents and bots for businesses. "
                "They can answer leads, qualify requests, automate support, send SMS follow-ups, and handle demos in a natural way so the customer clearly sees the value."
            )
        if "invoice" in source:
            return (
                "Yes, I can help with the invoice. From the information I have, the invoice is usually sent by email after payment confirmation, "
                "typically within 24 hours. If you want, we can immediately check whether you need it resent or need to update the email address."
            )
        if "delivery" in source or "order" in source:
            return (
                "Sure. From the information I have, delivery usually takes 1 to 3 business days. "
                "If you want, tell me when you placed the order and I’ll help estimate it more precisely."
            )
        return (
            f"From the information I have, the answer is: {kb_match.answer} "
            "If you want, I can turn that into a concrete next step for your case."
        )


    @staticmethod
    def _demo_reply(user_text: str, language: str, context: dict | None = None) -> str:
        lowered = user_text.lower()
        niche = "your business"
        website_summary = ""
        if isinstance(context, dict):
            website_summary = (context.get("website_context") or {}).get("summary", "")

        restaurant_markers = ["restaurant", "rezerv", "masa", "booking", "table", "menu"]
        if any(marker in lowered for marker in restaurant_markers):
            if language == "ro":
                base = (
                    "Sigur — iată un demo scurt și natural pentru rezervare la restaurant. "
                    "Client: «Bună, vreau o masă pentru 4 persoane vineri la 19:30.» "
                    "Agent: «Sigur, te ajut imediat. Confirm rezervarea pentru 4 persoane, vineri, la 19:30. "
                    "Pe ce nume fac rezervarea?» "
                    "Client: «Pe numele Andrei.» "
                    "Agent: «Perfect. Am notat rezervarea pe numele Andrei și îți trimit acum un SMS de confirmare cu data, ora și numărul de persoane.»"
                )
                if website_summary:
                    return f"{base} Pe site am văzut și context util: {website_summary[:180]}"
                return base

            base = (
                "Sure — here is a short, natural restaurant reservation demo. "
                "Customer: «Hi, I need a table for 4 on Friday at 7:30 PM.» "
                "Agent: «Absolutely, I can help with that. I’m confirming a reservation for 4 guests on Friday at 7:30 PM. "
                "What name should I place it under?» "
                "Customer: «Andrei.» "
                "Agent: «Perfect. I’ve noted the booking under Andrei and I’m sending an SMS confirmation now with the date, time, and party size.»"
            )
            if website_summary:
                return f"{base} I also checked the configured website and found: {website_summary[:180]}"
            return base

        if language == "ro":
            for marker in ["pentru ", "despre "]:
                if marker in lowered:
                    niche = user_text[lowered.index(marker) + len(marker):].strip(" .?!") or niche
                    break
            return (
                f"Sigur — îți fac un demo natural pentru zona {niche}. Imaginează-ți că sună un client, agentul răspunde, înțelege intenția, "
                "confirmă rapid detaliile importante, propune intervalul potrivit sau oferta potrivită, apoi trimite SMS ori programează următorul pas fără să pară un robot."
            )

        for marker in ["for ", "about "]:
            if marker in lowered:
                niche = user_text[lowered.index(marker) + len(marker):].strip(" .?!") or niche
                break
        return (
            f"Sure — here is a natural demo for the {niche} niche. Imagine a customer calling in, the agent answers naturally, understands the intent, "
            "confirms the important details, proposes the right slot or offer, and then sends an SMS or books the next step without sounding robotic."
        )

    @staticmethod
    def _natural_reply(user_text: str, language: str, skill_instruction: str | None, context: dict | None = None) -> str:
        lowered = user_text.lower()
        if "demo" in lowered or "demonstra" in lowered or "demonstre" in lowered:
            return MockLLMProvider._demo_reply(user_text, language, context)

        if language == "ro":
            if skill_instruction and "SALES" in skill_instruction:
                return (
                    "Sigur, hai să găsim varianta potrivită pentru tine. "
                    "Spune-mi ce vrei să obții și ce buget ai în minte, iar eu îți recomand cea mai bună opțiune."
                )
            return (
                f"În regulă, te ajut cu asta. Ai spus: „{user_text}”. "
                "Dă-mi încă un detaliu scurt și continuăm natural, ca într-o conversație normală."
            )

        if skill_instruction and "SALES" in skill_instruction:
            return (
                "Absolutely — let's find the best option for you. "
                "Tell me what outcome you want and the budget you have in mind, and I'll recommend the best fit."
            )
        return (
            f"Alright, I can help with that. You said: “{user_text}”. "
            "Give me one more short detail and we'll continue naturally from there."
        )

    async def generate(
        self,
        user_text: str,
        language: str,
        kb_match: KnowledgeMatch | None,
        context: dict,
        skill_instruction: str | None = None,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> str:
        history = conversation_history or []
        research = context.get("research") if isinstance(context, dict) else None
        website_context = context.get("website_context") if isinstance(context, dict) else None

        if research and research.get("status") in {"ok", "dry_run"}:
            summary = research.get("summary") or research.get("title") or ""
            if language == "ro":
                return f"Am verificat informația și iată pe scurt ce am găsit: {summary}"
            return f"I checked the information and here is the short version: {summary}"

        if website_context and website_context.get("status") == "ok":
            summary = website_context.get("summary") or website_context.get("title") or ""
            if language == "ro":
                return f"Am verificat site-ul configurat și iată ce este relevant: {summary}"
            return f"I checked the configured website and here is the relevant information: {summary}"

        if kb_match and kb_match.confidence >= 0.6:
            repeated = self._already_answered_kb(history, kb_match)
            is_invoice = "factura" in kb_match.source.lower() or "invoice" in kb_match.source.lower()

            if repeated and is_invoice:
                return self._invoice_follow_up(language)

            grounded = self._grounded_kb_reply(language, user_text, kb_match)
            citation = f" (Sursă: {kb_match.source})" if language == "ro" else f" (Source: {kb_match.source})"
            return f"{grounded}{citation}"

        return self._natural_reply(user_text, language, skill_instruction, context)


class OpenAILLMProvider:
    async def generate(
        self,
        user_text: str,
        language: str,
        kb_match: KnowledgeMatch | None,
        context: dict,
        skill_instruction: str | None = None,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> str:
        provider = settings.llm_provider.lower().strip()
        if provider == "groq":
            api_key = settings.groq_api_key
            model = settings.groq_model
            endpoint = settings.groq_base_url
        else:
            api_key = settings.openai_api_key
            model = settings.openai_model
            endpoint = settings.openai_base_url

        if not api_key:
            return await MockLLMProvider().generate(
                user_text,
                language,
                kb_match,
                context,
                skill_instruction,
                conversation_history,
            )

        language_name = "Romanian" if language == "ro" else "English"
        kb_text = kb_match.answer if kb_match else "No KB match found. Ask one concise clarifying question."
        kb_source = kb_match.source if kb_match else "none"
        history = conversation_history or []
        skill_prompt = skill_instruction or "No specific skill active."

        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a customer support voice agent in a live phone conversation. "
                        f"Business name: {settings.business_name}. "
                        f"Business domain: {settings.business_domain}. "
                        f"Agent display name: {settings.agent_name}. "
                        "Reply in the same language as the user. "
                        "Keep responses brief, natural, and human-sounding for speech. "
                        "Sound like a real chatbot assistant, not a rigid support script. "
                        "Use knowledge base evidence as grounding, but do not repeat FAQ wording verbatim unless absolutely necessary. "
                        "Do not sound like a rigid FAQ bot; sound like a helpful chatbot that is thinking through the user's case. "
                        "If the user repeats the same topic, do not repeat the same sentence verbatim; instead move the conversation forward with the next helpful question or action. "
                        "If web research or URL inspection results are present, weave them into the reply naturally like a real AI assistant. "
                        "If knowledge base evidence is present, mention the source label naturally. "
                        "If data is missing or confidence is low, ask one clarification question instead of inventing details. "
                        "Recommend a human handoff for billing disputes, legal requests, security concerns, or repeated failures. "
                        f"Behavior EN: {settings.behavior_style_en}. "
                        f"Behavior RO: {settings.behavior_style_ro}."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Language: {language_name}\n"
                        f"Skill instruction: {skill_prompt}\n"
                        f"Customer context: {context}\n"
                        f"Recent conversation turns: {history}\n"
                        f"KB source: {kb_source}\n"
                        f"KB answer: {kb_text}\n"
                        f"User: {user_text}"
                    ),
                },
            ],
            "temperature": 0.65,
        }

        async with httpx.AsyncClient(timeout=20) as client:
            res = await client.post(
                endpoint,
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
            res.raise_for_status()
            body = res.json()

        return body["choices"][0]["message"]["content"].strip()
