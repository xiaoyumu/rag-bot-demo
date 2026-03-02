from app.integrations.deepseek_llm import DeepSeekClient
from app.integrations.weaviate_client import RetrievedChunk


class AnswerGenerationService:
    def __init__(self, llm_client: DeepSeekClient) -> None:
        self.llm_client = llm_client

    async def generate_answer(
        self,
        user_question: str,
        rewritten_query: str,
        context_chunks: list[RetrievedChunk],
        history_messages: list[dict[str, str]] | None = None,
        profile_context: str | None = None,
    ) -> str:
        context_blocks: list[str] = []
        for idx, chunk in enumerate(context_chunks, start=1):
            context_blocks.append(
                f"[{idx}] source={chunk.source} chunk_id={chunk.chunk_id}\n{chunk.text}"
            )
        context_text = "\n\n".join(context_blocks)
        history_blocks: list[str] = []
        for message in history_messages or []:
            role = message.get("role", "").strip()
            content = message.get("content", "").strip()
            if role and content:
                history_blocks.append(f"{role}: {content}")
        history_text = "\n".join(history_blocks) if history_blocks else "(no prior messages)"
        profile_text = profile_context.strip() if profile_context and profile_context.strip() else "(empty)"

        system_prompt = (
            "You are a knowledge-base assistant. "
            "Answer strictly based on the given context. "
            "If context is insufficient, explicitly say you do not know."
        )
        user_prompt = (
            f"Profile context:\n{profile_text}\n\n"
            f"Conversation history:\n{history_text}\n\n"
            f"Original question:\n{user_question}\n\n"
            f"Retrieval query:\n{rewritten_query}\n\n"
            f"Context:\n{context_text}\n\n"
            "Please answer in Chinese and keep it concise."
        )
        return await self.llm_client.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
        )
