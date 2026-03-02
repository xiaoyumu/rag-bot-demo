from app.services.rag.prompt_budget import PromptBudgetManager


def test_trim_history_keeps_recent_within_budget() -> None:
    manager = PromptBudgetManager()
    messages = [
        {"role": "user", "content": "第一轮问题"},
        {"role": "assistant", "content": "第一轮回答"},
        {"role": "user", "content": "第二轮问题，内容更长一些用于测试预算裁剪。"},
        {"role": "assistant", "content": "第二轮回答，内容也更长一些用于测试预算裁剪。"},
    ]

    trimmed = manager.trim_history(messages=messages, max_tokens=25)

    assert trimmed
    assert trimmed[-1]["content"] == messages[-1]["content"]
    total_tokens = sum(manager.estimate_tokens_for_message(item) for item in trimmed)
    assert total_tokens <= 25


def test_trim_history_fallback_to_latest_message() -> None:
    manager = PromptBudgetManager()
    messages = [{"role": "user", "content": "非常非常长的内容" * 100}]

    trimmed = manager.trim_history(messages=messages, max_tokens=1)

    assert len(trimmed) == 1
    assert trimmed[0]["role"] == "user"
