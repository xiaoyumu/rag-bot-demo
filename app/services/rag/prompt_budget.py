class PromptBudgetManager:
    def estimate_tokens_for_text(self, text: str) -> int:
        stripped = text.strip()
        if not stripped:
            return 0
        # Approximation for mixed Chinese/English content.
        return max(1, int(len(stripped) / 2.8))

    def estimate_tokens_for_message(self, message: dict[str, str]) -> int:
        role = message.get("role", "")
        content = message.get("content", "")
        return self.estimate_tokens_for_text(role) + self.estimate_tokens_for_text(content) + 4

    def trim_history(
        self,
        messages: list[dict[str, str]],
        max_tokens: int,
    ) -> list[dict[str, str]]:
        if max_tokens <= 0 or not messages:
            return []

        selected_reversed: list[dict[str, str]] = []
        used_tokens = 0
        for message in reversed(messages):
            message_tokens = self.estimate_tokens_for_message(message)
            if message_tokens <= 0:
                continue
            if used_tokens + message_tokens > max_tokens:
                continue
            selected_reversed.append(message)
            used_tokens += message_tokens

        if selected_reversed:
            selected_reversed.reverse()
            return selected_reversed

        # If nothing fits, keep the latest non-empty message as a fallback.
        latest = messages[-1]
        latest_content = latest.get("content", "").strip()
        latest_role = latest.get("role", "").strip()
        if latest_content and latest_role:
            return [{"role": latest_role, "content": latest_content}]
        return []
