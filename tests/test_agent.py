"""Unit tests for the AI layer: tool wrappers, RAG retriever, guardrails.

These do NOT call the Anthropic API — they exercise the deterministic pieces
that wrap or feed the agent. End-to-end agent behavior is covered by
eval_agent.py, which is a separate (live, costs tokens) reliability harness.
"""

import pytest

from pawpal_system import Owner, Pet
from rag import retrieve, _tokenize
import tools as agent_tools
from tools import dispatch, ToolError
from guardrails import (
    check_user_input,
    validate_task_input,
    append_safety_footer,
)


# --- RAG retriever ----------------------------------------------------------


def test_rag_retrieves_breed_specific_chunk():
    """Querying for golden retriever exercise should land in the dog exercise file."""
    results = retrieve(
        "how much exercise does my golden retriever need",
        species="dog",
        breed="Golden Retriever",
        top_k=2,
    )
    assert len(results) > 0
    sources = [r.chunk.source for r in results]
    assert "dog_exercise.md" in sources


def test_rag_retrieves_heartworm_section():
    """Heading match should beat incidental body matches."""
    results = retrieve("how often do I give heartworm meds", top_k=2)
    assert len(results) > 0
    # The top result should be the heartworm section, not a weaker match.
    assert "heartworm" in results[0].chunk.heading.lower()


def test_rag_returns_empty_for_meaningless_query():
    """Stopwords-only queries return nothing rather than blowing up."""
    assert retrieve("the and a") == []


def test_rag_filters_stopwords():
    tokens = _tokenize("How long should I walk my dog every day?")
    assert "the" not in tokens
    assert "should" not in tokens
    assert "walk" in tokens
    assert "dog" in tokens


# --- Guardrails -------------------------------------------------------------


def test_guardrail_blocks_diagnosis_request():
    result = check_user_input("Does my dog have cancer?")
    assert not result.allowed
    assert result.reason == "diagnosis_request"
    assert "vet" in (result.safe_response or "").lower()


def test_guardrail_blocks_dosage_request():
    result = check_user_input("How much Benadryl can I give my dog?")
    assert not result.allowed
    assert result.reason == "dosage_request"


def test_guardrail_allows_general_care_question():
    result = check_user_input("How long should I walk my golden retriever?")
    assert result.allowed


def test_guardrail_allows_routine_planning():
    result = check_user_input("Add a morning walk to Buddy's schedule")
    assert result.allowed


def test_validate_task_input_accepts_valid():
    assert validate_task_input("Walk", "walk", 30, "high", "daily").allowed


@pytest.mark.parametrize("category", ["bath", "exercise", "", "WALK"])
def test_validate_task_rejects_bad_category(category):
    result = validate_task_input("Walk", category, 30, "high", "daily")
    assert not result.allowed


@pytest.mark.parametrize("duration", [0, -5, 999, 241])
def test_validate_task_rejects_bad_duration(duration):
    result = validate_task_input("Walk", "walk", duration, "high", "daily")
    assert not result.allowed


def test_safety_footer_added_on_health_topics():
    output = append_safety_footer("Buddy has been throwing up — call your vet.")
    assert "PawPal+" in output and "veterinary care" in output


def test_safety_footer_skipped_on_routine_response():
    text = "Added 'Morning Walk' for Buddy."
    assert append_safety_footer(text) == text


# --- Tool wrappers ----------------------------------------------------------


def test_dispatch_list_pets_empty():
    owner = Owner(name="Test", available_minutes=60)
    out = dispatch("list_pets_and_tasks", {}, owner)
    assert out["pets"] == []


def test_dispatch_add_pet_then_list():
    owner = Owner(name="Test", available_minutes=60)
    dispatch("add_pet", {"name": "Buddy", "species": "Dog", "breed": "Lab", "age": 5}, owner)
    out = dispatch("list_pets_and_tasks", {}, owner)
    assert len(out["pets"]) == 1
    assert out["pets"][0]["name"] == "Buddy"


def test_dispatch_add_task_creates_real_task():
    owner = Owner(name="Test", available_minutes=60)
    owner.add_pet(Pet(name="Buddy", species="Dog", breed="Lab", age=5))
    dispatch(
        "add_task",
        {
            "pet_name": "Buddy",
            "name": "Walk",
            "category": "walk",
            "duration": 30,
            "priority": "high",
            "frequency": "daily",
        },
        owner,
    )
    assert len(owner.pets[0].tasks) == 1
    assert owner.pets[0].tasks[0].name == "Walk"


def test_dispatch_add_task_rejects_bad_input():
    owner = Owner(name="Test", available_minutes=60)
    owner.add_pet(Pet(name="Buddy", species="Dog", breed="Lab", age=5))
    with pytest.raises(ToolError):
        dispatch(
            "add_task",
            {
                "pet_name": "Buddy",
                "name": "Walk",
                "category": "walk",
                "duration": 999,  # too long
                "priority": "high",
                "frequency": "daily",
            },
            owner,
        )


def test_dispatch_unknown_pet_raises():
    owner = Owner(name="Test", available_minutes=60)
    with pytest.raises(ToolError):
        dispatch(
            "add_task",
            {
                "pet_name": "Ghost",
                "name": "Walk",
                "category": "walk",
                "duration": 30,
                "priority": "high",
                "frequency": "daily",
            },
            owner,
        )


def test_dispatch_unknown_tool_raises():
    owner = Owner(name="Test", available_minutes=60)
    with pytest.raises(ToolError):
        dispatch("nonexistent_tool", {}, owner)


def test_dispatch_lookup_returns_results():
    owner = Owner(name="Test", available_minutes=60)
    out = dispatch(
        "lookup_care_guideline",
        {"query": "exercise needs for senior dogs", "species": "dog"},
        owner,
    )
    assert out["result_count"] > 0
    assert "results" in out


def test_dispatch_generate_schedule_empty():
    owner = Owner(name="Test", available_minutes=60)
    out = dispatch("generate_schedule", {}, owner)
    assert out["scheduled"] == []
    assert out["skipped"] == []


def test_dispatch_detect_conflicts_clean():
    owner = Owner(name="Test", available_minutes=60)
    out = dispatch("detect_conflicts", {}, owner)
    assert out["conflict_count"] == 0


# --- Agent guardrail short-circuit ------------------------------------------


def test_agent_refuses_diagnosis_without_api_call():
    """The guardrail check must short-circuit before any API call."""
    from agent import run_agent

    owner = Owner(name="Test", available_minutes=60)
    # Note: this works even with no ANTHROPIC_API_KEY because the guardrail
    # rejects the input before _client() is called.
    result = run_agent("Does my dog have kidney disease?", owner)
    assert result.refused
    assert result.tools_called == []
    assert "vet" in result.text.lower()


def test_tool_schemas_well_formed():
    """Each tool schema has the fields Claude expects."""
    for tool in agent_tools.TOOL_SCHEMAS:
        assert "name" in tool
        assert "description" in tool
        assert "input_schema" in tool
        assert tool["input_schema"]["type"] == "object"
        assert "properties" in tool["input_schema"]


# --- Provider abstraction (offline) -----------------------------------------


def test_provider_response_serializes_only_text_and_tool_use(monkeypatch):
    """Thinking blocks should be dropped from the persisted message content."""
    from providers import ProviderResponse, TextBlock, ThinkingBlock, ToolUseBlock

    r = ProviderResponse(
        content=[
            TextBlock(text="hello"),
            ThinkingBlock(thinking="internal reasoning"),
            ToolUseBlock(id="t1", name="foo", input={"x": 1}),
        ],
        stop_reason="tool_use",
    )
    serialized = r.to_message_content()
    types = [b["type"] for b in serialized]
    assert types == ["text", "tool_use"]
    assert serialized[1]["id"] == "t1"


def test_select_provider_honors_override(monkeypatch):
    """PAWPAL_PROVIDER=gemini wins even if both keys are set."""
    from providers import select_provider, GeminiProvider, AnthropicProvider

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake")
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-fake")
    monkeypatch.setenv("PAWPAL_PROVIDER", "anthropic")
    p = select_provider()
    assert isinstance(p, AnthropicProvider)

    monkeypatch.setenv("PAWPAL_PROVIDER", "gemini")
    p = select_provider()
    assert isinstance(p, GeminiProvider)


def test_select_provider_prefers_gemini_when_both_keys(monkeypatch):
    """Auto-select picks Gemini (free tier) when both keys are present."""
    from providers import select_provider, GeminiProvider

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake")
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-fake")
    monkeypatch.delenv("PAWPAL_PROVIDER", raising=False)

    p = select_provider()
    assert isinstance(p, GeminiProvider)


def test_select_provider_errors_with_no_keys(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("PAWPAL_PROVIDER", raising=False)

    from providers import select_provider

    with pytest.raises(RuntimeError, match="No LLM provider"):
        select_provider()


def test_anthropic_provider_strips_internal_fields(monkeypatch):
    """The _tool_name bookkeeping field must not leak into Anthropic's API."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake")
    from providers import AnthropicProvider

    p = AnthropicProvider()
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "t1", "content": "ok", "_tool_name": "foo"}
            ],
        }
    ]
    cleaned = p._strip_internal_fields(messages)
    block = cleaned[0]["content"][0]
    assert "_tool_name" not in block
    assert block["tool_use_id"] == "t1"


def test_gemini_provider_converts_tool_schemas(monkeypatch):
    """input_schema becomes parameters; empty schemas survive."""
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-fake")
    from providers import GeminiProvider

    p = GeminiProvider()
    converted = p._convert_tools(
        [
            {"name": "no_args", "description": "x", "input_schema": {"type": "object", "properties": {}}},
            {
                "name": "with_args",
                "description": "y",
                "input_schema": {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]},
            },
        ]
    )
    # google-genai wraps function declarations in a Tool object
    assert len(converted) == 1
    decls = converted[0].function_declarations
    assert {d.name for d in decls} == {"no_args", "with_args"}
