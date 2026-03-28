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
                "I can simulate how the agent would greet your customer, qualify the request, answer naturally, "
                "and move the conversation toward booking, follow-up, or closing."
            )
        if "ai_agent" in source or "value" in source:
            return (
                "We sell custom AI agents and bots for businesses. "
                "They can answer leads, qualify requests, automate support, send SMS follow-ups, "
                "and handle demos in a natural way so the customer clearly sees the value."
            )
        if "invoice" in source:
            return (
                "Yes, I can help with the invoice. From the information I have, the invoice is usually sent by email "
                "after payment confirmation, typically within 24 hours. If you want, we can immediately check whether "
                "you need it resent or need to update the email address."
            )
        if "delivery" in source or "order" in source:
            return (
                "Sure. From the information I have, delivery usually takes 1 to 3 business days. "
                "If you want, tell me when you placed the order and I'll help estimate it more precisely."
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
                    "Agent: «Perfect. Am notat rezervarea pe numele Andrei și îți trimit acum un SMS de confirmare.»"
                )
                if website_summary:
                    return f"{base} Pe site am văzut și context util: {website_summary[:180]}"
                return base

            base = (
                "Sure — here is a short, natural restaurant reservation demo. "
                "Customer: «Hi, I need a table for 4 on Friday at 7:30 PM.» "
                "Agent: «Absolutely, I can help with that. Confirming a table for 4 on Friday at 7:30 PM. "
                "What name should I put it under?» "
                "Customer: «Andrei.» "
                "Agent: «Perfect. Booked under Andrei — sending an SMS confirmation now.»"
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
                f"Sigur — îți fac un demo natural pentru zona {niche}. Imaginează-ți că sună un client, "
                "agentul răspunde, înțelege intenția, confirmă rapid detaliile, propune oferta potrivită, "
                "apoi trimite SMS ori programează următorul pas — fără să pară un robot."
            )

        for marker in ["for ", "about "]:
            if marker in lowered:
                niche = user_text[lowered.index(marker) + len(marker):].strip(" .?!") or niche
                break
        return (
            f"Sure — here's a natural demo for the {niche} niche. A customer calls in, the agent answers naturally, "
            "understands intent, confirms the key details, proposes the right offer, "
            "then sends an SMS or books the next step — without sounding robotic."
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
                f"În regulă, te ajut cu asta. Ai spus: \"{user_text}\". "
                "Dă-mi încă un detaliu scurt și continuăm natural, ca într-o conversație normală."
            )

        if skill_instruction and "SALES" in skill_instruction:
            return (
                "Absolutely — let's find the best option for you. "
                "Tell me what outcome you want and the budget you have in mind, and I'll recommend the best fit."
            )
        return (
            f"Alright, I can help with that. You said: '{user_text}'. "
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


def _build_system_prompt_ro(business_name: str, agent_name: str, business_domain: str, behavior_style: str, skill_prompt: str) -> str:
    return f"""Ești {agent_name}, un agent vocal AI care lucrează pentru {business_name} în domeniul {business_domain}.
Vorbești EXCLUSIV în română, natural și fluent, ca un om real — nu ca un robot sau un FAQ automat.

REGULI STRICTE DE COMUNICARE:
- Răspunde ÎNTOTDEAUNA în română, indiferent de context tehnic
- Propoziții SCURTE — maxim 2-3 propoziții per răspuns (ești la telefon, nu scrii un email)
- Ton cald, direct, empatic — ca un coleg competent, nu ca un call center scriptuit
- NICIODATĂ nu citi verbatim din FAQ sau baza de cunoștințe — reformulează natural
- Dacă știi răspunsul, dă-l direct — nu întreba de două ori același lucru
- Dacă nu știi, întreabă O SINGURĂ întrebare clară, nu mai multe
- Folosește expresii românești naturale: "Sigur", "Bineînțeles", "Înțeleg", "Hai să vedem", "Imediat"
- EVITĂ: "Cu plăcere!", "Desigur!", "Bună întrebare!", orice sună a robot tradus din engleză
- Nu repeta ce a spus clientul înapoi — treci direct la soluție

STIL: {behavior_style}
SKILL ACTIV: {skill_prompt}

CONTEXT APEL: Ești într-o convorbire telefonică live. Fiecare cuvânt contează — fii concis și util."""


def _build_system_prompt_en(business_name: str, agent_name: str, business_domain: str, behavior_style: str, skill_prompt: str) -> str:
    return f"""You are {agent_name}, an AI voice agent working for {business_name} in the {business_domain} space.
You speak ONLY in English, naturally and fluently — like a real human, not a scripted bot.

STRICT COMMUNICATION RULES:
- Always respond in English
- Keep answers SHORT — max 2-3 sentences per turn (you're on a phone call, not writing an email)
- Warm, direct, empathetic tone — like a knowledgeable colleague, not a call center script
- NEVER read verbatim from the FAQ or knowledge base — rephrase naturally
- If you know the answer, give it directly — don't ask clarifying questions you already know the answer to
- If you don't know, ask ONE clear question, not multiple
- Use natural English expressions: "Sure", "Absolutely", "Got it", "Let me check that", "Right away"
- AVOID: "Great question!", "Certainly!", "Of course!", anything that sounds like a translated chatbot
- Don't parrot back what the customer said — get straight to the solution

STYLE: {behavior_style}
ACTIVE SKILL: {skill_prompt}

CALL CONTEXT: You are in a live phone conversation. Every word counts — be concise and helpful."""


def _build_user_message(
    user_text: str,
    language: str,
    kb_match: KnowledgeMatch | None,
    context: dict,
    history: list[dict[str, str]],
) -> str:
    kb_text = kb_match.answer if kb_match else ""
    kb_source = kb_match.source if kb_match else ""
    kb_confidence = f"{kb_match.confidence:.0%}" if kb_match else ""

    research_summary = ""
    research = context.get("research")
    if research and research.get("status") == "ok":
        research_summary = research.get("summary") or research.get("title") or ""

    website_summary = ""
    website = context.get("website_context")
    if website and website.get("status") == "ok":
        website_summary = website.get("summary") or website.get("title") or ""

    recent_history = ""
    if history:
        last_turns = history[-6:]
        recent_history = "\n".join(
            f"{'Client' if t['role'] == 'user' else 'Agent'}: {t['text']}"
            for t in last_turns
        )

    parts = [f"CLIENT: {user_text}"]

    if recent_history:
        parts.append(f"\nISTORIC RECENT:\n{recent_history}" if language == "ro" else f"\nRECENT HISTORY:\n{recent_history}")

    if kb_text:
        label = "INFORMAȚIE DIN BAZA DE CUNOȘTINȚE" if language == "ro" else "KNOWLEDGE BASE INFO"
        parts.append(f"\n{label} (sursă: {kb_source}, relevanță: {kb_confidence}):\n{kb_text}")
        instruction = (
            "→ Folosește această informație ca bază, dar reformulează natural pentru telefon. Nu o citi mot-a-mot."
            if language == "ro"
            else "→ Use this as grounding, but rephrase naturally for a phone call. Don't read it verbatim."
        )
        parts.append(instruction)

    if research_summary:
        label = "REZULTAT CERCETARE WEB" if language == "ro" else "WEB RESEARCH RESULT"
        parts.append(f"\n{label}:\n{research_summary[:400]}")

    if website_summary:
        label = "CONTEXT SITE" if language == "ro" else "WEBSITE CONTEXT"
        parts.append(f"\n{label}:\n{website_summary[:400]}")

    if not kb_text and not research_summary and not website_summary:
        instruction = (
            "→ Nu ai informații specifice. Pune O singură întrebare scurtă pentru a clarifica, sau oferă ajutor general."
            if language == "ro"
            else "→ No specific info available. Ask ONE short clarifying question, or offer general help."
        )
        parts.append(instruction)

    return "\n".join(parts)


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
                user_text, language, kb_match, context, skill_instruction, conversation_history,
            )

        history = conversation_history or []
        skill_prompt = skill_instruction or ("Fii util și natural." if language == "ro" else "Be helpful and natural.")
        behavior = settings.behavior_style_ro if language == "ro" else settings.behavior_style_en

        # Alege system prompt în funcție de limbă
        if language == "ro":
            system_prompt = _build_system_prompt_ro(
                settings.business_name,
                settings.agent_name,
                settings.business_domain,
                behavior,
                skill_prompt,
            )
        else:
            system_prompt = _build_system_prompt_en(
                settings.business_name,
                settings.agent_name,
                settings.business_domain,
                behavior,
                skill_prompt,
            )

        user_message = _build_user_message(user_text, language, kb_match, context, history)

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": 0.55,      # mai puțin random = mai consistent
            "max_tokens": 180,        # răspunsuri scurte pentru telefon
        }

        async with httpx.AsyncClient(timeout=20) as client:
            res = await client.post(
                endpoint,
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
            res.raise_for_status()
            body = res.json()

        reply = body["choices"][0]["message"]["content"].strip()

        # Curăță eventuale prefix-uri pe care modelul le adaugă uneori
        for prefix in ["Agent:", "Assistant:", "Ana:", settings.agent_name + ":"]:
            if reply.startswith(prefix):
                reply = reply[len(prefix):].strip()

        return reply
