from app.services.rag.profile_memory import extract_profile_patch, render_profile_context


def test_extract_profile_patch_for_language_style_and_constraints() -> None:
    patch = extract_profile_patch("请用中文简洁回答，不要联网，也不要猜测。")

    assert patch["language"] == "zh-CN"
    assert patch["style"] == "concise"
    assert "no_network" in patch["constraints"]
    assert "no_guessing" in patch["constraints"]


def test_render_profile_context_is_stable() -> None:
    context = render_profile_context(
        {
            "language": "zh-CN",
            "style": "concise",
            "constraints": ["no_network", "context_only"],
        }
    )

    assert "Preferred language" in context
    assert "Response style" in context
    assert "Constraints" in context
