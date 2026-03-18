from typing import Protocol

import httpx

from app.config import settings


class LLMProvider(Protocol):
    async def generate(
        self,
        user_text: str,
        language: str,
        kb_answer: str | None,
        context: dict,
        skill_instruction: str | None = None,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> str:
        ...


class MockLLMProvider:
    async def generate(
        self,
        user_text: str,
        language: str,
        kb_answer: str | None,
        context: dict,
        skill_instruction: str | None = None,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> str:
        if kb_answer:
            return kb_answer

        skill_text = f" [{skill_instruction}]" if skill_instruction else ""
        if language == "ro":
            return (
                f"Salut! Sunt {settings.agent_name} de la {settings.business_name}.{skill_text} "
                "Te ajut cu drag. Spune-mi, te rog, câteva detalii și rezolvăm împreună."
            )

        return (
            f"Hi! I'm {settings.agent_name} from {settings.business_name}.{skill_text} "
            "Happy to help. Please share a few details and we’ll sort this out together."
        )


class OpenAILLMProvider:
    async def generate(
        self,
        user_text: str,
        language: str,
        kb_answer: str | None,
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
                kb_answer,
                context,
                skill_instruction,
                conversation_history,
            )

        language_name = "Romanian" if language == "ro" else "English"
        context_text = kb_answer or "No KB match found. Ask concise clarification question."
        skill_prompt = skill_instruction or "No specific skill active."
        history = conversation_history or []

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
                        "Sound like a human support rep: warm, natural, short spoken phrases, no robotic style. "
                        "Acknowledge user emotion briefly, then provide actionable help. "
                        "Ask at most one follow-up question at a time. "
                        "Do not invent policy details. "
                        "Use available customer context and be concise. "
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
                        f"KB: {context_text}\n"
                        f"User: {user_text}"
                    ),
                },
            ],
            "temperature": 0.45,
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
