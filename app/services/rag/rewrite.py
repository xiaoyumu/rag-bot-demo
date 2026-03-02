from app.integrations.deepseek_llm import DeepSeekClient


class QuestionRewriteService:
    def __init__(self, llm_client: DeepSeekClient) -> None:
        self.llm_client = llm_client

    async def rewrite(
        self,
        question: str,
        history_messages: list[dict[str, str]] | None = None,
        profile_context: str | None = None,
    ) -> str:
        system_prompt = (
            "You rewrite user questions for knowledge-base retrieval. "
            "Return only one concise rewritten query in the same language as user input. "
            "Do not answer the question."
        )
        history_lines: list[str] = []
        for message in history_messages or []:
            role = message.get("role", "").strip()
            content = message.get("content", "").strip()
            if role and content:
                history_lines.append(f"{role}: {content}")
        history_text = "\n".join(history_lines) if history_lines else "(empty)"
        profile_text = profile_context.strip() if profile_context and profile_context.strip() else "(empty)"
        user_content = (
            f"Profile context:\n{profile_text}\n\n"
            f"Conversation history:\n{history_text}\n\n"
            f"Current user question:\n{question}\n\n"
            "Rewrite the current user question into a retrieval-friendly query."
        )

        rewritten = await self.llm_client.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.0,
        )
        return rewritten or question
