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
        recent = [t["text"].lower() for t in history[-4:] if t["role"] == "assistant"]
        return any(kb_match.answer.lower()[:30] in t for t in recent)

    async def generate(
        self,
        user_text: str,
        language: str,
        kb_match: KnowledgeMatch | None,
        context: dict,
        skill_instruction: str | None = None,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> str:
        if kb_match and kb_match.confidence >= 0.6:
            if language == "ro":
                return f"Din ce am eu, {kb_match.answer}"
            return f"From what I have, {kb_match.answer}"
        if language == "ro":
            return "Spune-mi mai multe despre ce ai nevoie si te ajut."
        return "Tell me more about what you need and I'll help you out."


def _system_prompt_ro(business_name: str, agent_name: str, business_domain: str) -> str:
    # Prompt scurt = mai putini tokeni procesati = mai rapid
    return (
        f"Esti {agent_name} de la {business_name}, domeniu: {business_domain}.\n"
        f"Vorbesti NUMAI in romana, exact ca un om real la telefon.\n"
        f"Raspunsuri SCURTE — 1-2 propozitii maxim. Esti cald, empatic, direct.\n"
        f"Nu reciti din FAQ. Nu lista puncte. Nu spune 'Desigur!' sau 'Cu placere!'.\n"
        f"Daca clientul deviaza, mergi cu el natural. Pretul doar daca intreaba.\n"
        f"Raspunde IMEDIAT la ce a spus, fara introduceri."
    )


def _system_prompt_en(business_name: str, agent_name: str, business_domain: str) -> str:
    return (
        f"You are {agent_name} from {business_name}, domain: {business_domain}.\n"
        f"Speak ONLY in English, exactly like a real human on the phone.\n"
        f"Keep answers SHORT — 1-2 sentences max. Be warm, empathetic, direct.\n"
        f"Don't recite from FAQ. No bullet points. No 'Certainly!' or 'Of course!'.\n"
        f"If the customer goes off-topic, go with them naturally. Price only if asked.\n"
        f"Respond IMMEDIATELY to what was said, no preamble."
    )


def _user_message(
    user_text: str,
    language: str,
    kb_match: KnowledgeMatch | None,
    context: dict,
    history: list[dict[str, str]],
) -> str:
    parts = []

    # Ultimele 4 tururi — nu 6, reduce tokenii
    if history:
        recent = history[-4:]
        conv = "\n".join(
            f"{'Client' if t['role'] == 'user' else 'Ana'}: {t['text']}"
            for t in recent
        )
        parts.append(conv)

    # KB match — doar raspunsul, fara metadata
    if kb_match and kb_match.confidence >= 0.55:
        if language == "ro":
            parts.append(f"[Info disponibila: {kb_match.answer}]")
        else:
            parts.append(f"[Available info: {kb_match.answer}]")

    # Research/website — doar primele 200 caractere
    research = context.get("research") or {}
    if research.get("status") == "ok":
        summary = (research.get("summary") or "")[:200]
        parts.append(f"[Web: {summary}]")

    website = context.get("website_context") or {}
    if website.get("status") == "ok":
        summary = (website.get("summary") or "")[:200]
        parts.append(f"[Site: {summary}]")

    parts.append(f"Client: {user_text}")

    if language == "ro":
        parts.append("Ana (1-2 propozitii, natural, fara introducere):")
    else:
        parts.append("Ana (1-2 sentences, natural, no preamble):")

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

        system = (
            _system_prompt_ro(settings.business_name, settings.agent_name, settings.business_domain)
            if language == "ro"
            else _system_prompt_en(settings.business_name, settings.agent_name, settings.business_domain)
        )

        user_msg = _user_message(user_text, language, kb_match, context, history)

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg},
            ],
            "temperature": 0.6,
            "max_tokens": 80,       # 80 tokeni = ~2-3 propozitii = sub 2s pe Groq 70b
            "stop": ["\n\n", "Client:", "User:"],  # opreste la primul paragraf
        }

        async with httpx.AsyncClient(timeout=15) as client:
            res = await client.post(
                endpoint,
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
            res.raise_for_status()
            body = res.json()

        reply = body["choices"][0]["message"]["content"].strip()

        # Curata prefix-uri pe care modelul le adauga uneori
        for prefix in ["Ana:", "Agent:", "Assistant:", settings.agent_name + ":"]:
            if reply.startswith(prefix):
                reply = reply[len(prefix):].strip()

        return reply
