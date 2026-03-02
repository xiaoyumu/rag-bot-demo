import httpx


class DeepSeekClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: int = 60,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key.strip()
        self.model = model
        self.timeout_seconds = timeout_seconds

        if not self.api_key:
            raise ValueError("DEEPSEEK_API_KEY is not configured.")

    async def chat(self, messages: list[dict[str, str]], temperature: float = 0.1) -> str:
        response = await self._post_chat(messages=messages, temperature=temperature)
        choices = response.get("choices") or []
        if not choices:
            raise ValueError("DeepSeek response does not contain choices.")
        content = choices[0].get("message", {}).get("content")
        if not isinstance(content, str):
            raise ValueError("DeepSeek response content is invalid.")
        return content.strip()

    async def _post_chat(
        self,
        messages: list[dict[str, str]],
        temperature: float,
    ) -> dict:
        if not self.api_key:
            raise ValueError("DEEPSEEK_API_KEY is not configured.")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            return response.json()
