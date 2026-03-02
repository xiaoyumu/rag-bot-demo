from collections.abc import Iterable


def extract_profile_patch(user_text: str) -> dict[str, object]:
    text = user_text.strip()
    if not text:
        return {}

    normalized = text.lower()
    patch: dict[str, object] = {}
    constraints: set[str] = set()

    if any(token in text for token in ("中文", "简体")):
        patch["language"] = "zh-CN"
    elif any(token in normalized for token in ("english", "英文")):
        patch["language"] = "en-US"

    if any(token in text for token in ("简洁", "简短", "精简")):
        patch["style"] = "concise"
    elif any(token in text for token in ("详细", "展开", "具体", "深入")):
        patch["style"] = "detailed"

    if any(token in text for token in ("不要联网", "不能联网", "禁止联网", "离线")):
        constraints.add("no_network")
    if any(token in text for token in ("不要猜", "不要臆测", "不要编造", "不知道就说不知道")):
        constraints.add("no_guessing")
    if any(token in text for token in ("仅基于上下文", "只根据上下文", "基于提供的资料", "不要使用外部知识")):
        constraints.add("context_only")

    if constraints:
        patch["constraints"] = sorted(constraints)
    return patch


def render_profile_context(profile: dict[str, object], max_items: int = 6) -> str:
    if not profile or max_items <= 0:
        return ""

    lines: list[str] = []
    language = profile.get("language")
    style = profile.get("style")
    constraints = _normalize_str_list(profile.get("constraints"))

    if isinstance(language, str) and language.strip():
        lines.append(f"- Preferred language: {language.strip()}")
    if isinstance(style, str) and style.strip():
        lines.append(f"- Response style: {style.strip()}")
    if constraints:
        lines.append(f"- Constraints: {', '.join(constraints)}")

    if not lines:
        return ""
    return "\n".join(lines[:max_items])


def _normalize_str_list(raw: object) -> list[str]:
    if not isinstance(raw, Iterable) or isinstance(raw, (str, bytes)):
        return []
    values = [str(item).strip() for item in raw if isinstance(item, str) and item.strip()]
    return sorted(set(values))
