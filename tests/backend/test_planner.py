"""Prompt-policy regression tests."""

from backend.core.planner import system_prompt


def test_github_profile_requests_never_use_a_hard_coded_repository(registry):
    prompt = system_prompt(registry)

    assert "garethdmm/griffin" not in prompt
    assert "ask for one" in prompt
    assert "Never infer an" in prompt
    assert "account, substitute a repository name" in prompt
    assert "https://github.com/<username>?tab=repositories" in prompt
