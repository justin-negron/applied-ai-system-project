"""PawPal+ Agent — Claude tool-calling loop.

Architecture: a manual agentic loop that lets Claude orchestrate the existing
`pawpal_system` operations through tool calls. Every step (planning, tool
input, tool result, confidence) is logged so the reasoning trace is
inspectable in the UI and the eval harness.

Why manual loop instead of the SDK tool runner: we need fine-grained
observability for the demo and the eval. The runner hides per-step state.
"""

from dataclasses import dataclass, field
import json
import os
from typing import Any, Optional

from dotenv import load_dotenv

import agent_logger
import tools as agent_tools
from guardrails import check_user_input, append_safety_footer
from pawpal_system import Owner
from providers import Provider, select_provider

load_dotenv()

MAX_TURNS = 8  # Hard cap on tool-calling iterations per user message.
MAX_TOKENS = 1024  # Anthropic free tier: 4K output tokens/min across 5 RPM → ~800/call.

SYSTEM_PROMPT = """You are PawPal+, an AI assistant that helps pet owners manage daily pet care tasks. You have tools to read/modify pet and task data, manage employees, and search a curated knowledge base.

# Rules
1. Call `list_pets_and_tasks` first if you don't know the current state.
2. Call `lookup_care_guideline` before recommending durations, frequencies, or care practices. Cite the source.
3. When asked to add/schedule/complete tasks, call the tool — don't just describe it.
4. Call `detect_conflicts` before generating a schedule or after adding multiple tasks.
5. End every response with "Confidence: <0.0–1.0>" and one sentence explaining it.

# Employee assignment
6. To assign today's work to employees, call `assign_tasks_to_employees`. It distributes highest-priority tasks first to whoever has the most remaining time.
7. Call `list_employees` before assigning to confirm who is working and how many minutes each has.

# Adding pets — always clarify first
8. Before calling `add_pet`, confirm the pet's species, breed, and age. If the user hasn't provided any of these, ask for them explicitly. Do not use placeholders like "unknown" — get the real values first.

# Hard limits — never break
- No medical diagnoses. Symptoms → tell them to see a vet.
- No medication dosages. Prescribed cadences only (e.g. "monthly heartworm pill").
- No invented data. If it's not in the system or knowledge base, say so.

# Tone
Concise, warm, practical."""


@dataclass
class AgentStep:
    """One observable step in the agent's reasoning trace."""

    kind: str  # "thinking" | "tool_call" | "tool_result" | "text" | "error"
    payload: dict[str, Any]


@dataclass
class AgentResult:
    text: str
    steps: list[AgentStep] = field(default_factory=list)
    refused: bool = False
    confidence: Optional[float] = None
    tools_called: list[str] = field(default_factory=list)
    turns_used: int = 0
    provider: str = ""
    model: str = ""


def _extract_confidence(text: str) -> Optional[float]:
    """Pull a 'Confidence: 0.85' value out of the model's text if present."""
    import re

    match = re.search(r"confidence[:\s]+([01](?:\.\d+)?)", text.lower())
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


def run_agent(
    user_message: str,
    owner: Owner,
    conversation_history: Optional[list[dict[str, Any]]] = None,
    provider: Optional[Provider] = None,
) -> AgentResult:
    """Run one user-message turn through the agent.

    Pass `conversation_history` to continue a multi-turn conversation. Each
    call appends the user message + assistant response to it (in place).
    Pass `provider` to override the auto-selected LLM provider.
    """
    result = AgentResult(text="", steps=[])
    agent_logger.log_event("user_message", {"text": user_message})

    # Guardrail: refuse diagnosis/dosage requests before spending tokens.
    guard = check_user_input(user_message)
    if not guard.allowed:
        result.text = guard.safe_response or "I can't help with that request."
        result.refused = True
        result.steps.append(AgentStep("error", {"reason": guard.reason, "message": result.text}))
        agent_logger.log_event("refused", {"reason": guard.reason})
        if conversation_history is not None:
            conversation_history.append({"role": "user", "content": user_message})
            conversation_history.append({"role": "assistant", "content": result.text})
        return result

    if provider is None:
        provider = select_provider()
    result.provider = provider.name
    result.model = provider.model
    agent_logger.log_event("provider_selected", {"provider": provider.name, "model": provider.model})

    messages: list[dict[str, Any]] = list(conversation_history) if conversation_history else []
    messages.append({"role": "user", "content": user_message})

    # Track the most recent tool name for each tool_use_id so the Gemini
    # provider can name function_response parts correctly.
    tool_name_by_id: dict[str, str] = {}

    final_text = ""
    for turn in range(MAX_TURNS):
        result.turns_used = turn + 1
        try:
            response = provider.call(
                system=SYSTEM_PROMPT,
                messages=messages,
                tools=agent_tools.TOOL_SCHEMAS,
                max_tokens=MAX_TOKENS,
            )
        except Exception as e:
            err = f"{provider.name} provider error: {type(e).__name__}: {e}"
            result.steps.append(AgentStep("error", {"message": err}))
            agent_logger.log_event("api_error", {"provider": provider.name, "error": err})
            result.text = (
                f"Sorry — the {provider.name} provider hit an error: {e}. "
                "Check your API key, model name, and connection, then try again."
            )
            return result

        # Surface text and thinking blocks for the trace.
        for block in response.content:
            if block.type == "text" and block.text:
                result.steps.append(AgentStep("text", {"text": block.text}))
                final_text += block.text + "\n"
            elif block.type == "thinking" and block.thinking:
                result.steps.append(AgentStep("thinking", {"text": block.thinking}))

        if response.stop_reason == "end_turn":
            break

        if response.stop_reason != "tool_use":
            result.steps.append(
                AgentStep("error", {"stop_reason": response.stop_reason, "note": "Unexpected stop reason."})
            )
            break

        # Persist the assistant's full content (including tool_use blocks) so
        # the next turn includes them. Stash the provider-native content too —
        # Gemini needs the original Content (with thought_signatures) for
        # function-call round-trips on thinking models.
        assistant_msg: dict[str, Any] = {
            "role": "assistant",
            "content": response.to_message_content(),
        }
        if response.provider == "gemini" and response.raw is not None:
            assistant_msg["_gemini_content"] = response.raw
        messages.append(assistant_msg)

        # Execute every requested tool.
        tool_results: list[dict[str, Any]] = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            tool_name = block.name
            tool_input = block.input
            tool_name_by_id[block.id] = tool_name
            result.tools_called.append(tool_name)
            agent_logger.log_event("tool_call", {"tool": tool_name, "input": tool_input})
            result.steps.append(AgentStep("tool_call", {"name": tool_name, "input": tool_input}))

            try:
                output = agent_tools.dispatch(tool_name, tool_input, owner)
                output_str = json.dumps(output, default=str, indent=2)
                is_error = False
            except agent_tools.ToolError as e:
                output_str = str(e)
                is_error = True
            except Exception as e:
                output_str = f"Internal error: {type(e).__name__}: {e}"
                is_error = True

            agent_logger.log_event(
                "tool_result", {"tool": tool_name, "is_error": is_error, "output": output_str[:500]}
            )
            result.steps.append(
                AgentStep(
                    "tool_result",
                    {"name": tool_name, "is_error": is_error, "output": output_str},
                )
            )

            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": output_str,
                    "is_error": is_error,
                    # Internal field: AnthropicProvider strips this; the Gemini
                    # provider uses it as the function_response name.
                    "_tool_name": tool_name,
                }
            )

        messages.append({"role": "user", "content": tool_results})
    else:
        # We hit MAX_TURNS without an end_turn.
        result.steps.append(AgentStep("error", {"message": f"Hit turn cap ({MAX_TURNS})."}))
        agent_logger.log_event("turn_cap_hit", {"max_turns": MAX_TURNS})

    # Empty-response recovery: if the model used tools but produced no text
    # at the end (a known Gemini quirk where the model returns just a
    # thought_signature), prompt once for a summary instead of giving up. We
    # don't want a silent "(no response generated)" when there's real work to
    # report on.
    final_text = final_text.strip()
    if not final_text and result.tools_called and result.turns_used < MAX_TURNS:
        agent_logger.log_event("empty_response_nudge", {"after_turns": result.turns_used})
        nudge = (
            "Please give me a brief summary of what you found or did, and your "
            "confidence rating. Don't call any more tools — just summarize."
        )
        messages.append({"role": "user", "content": nudge})
        try:
            response = provider.call(
                system=SYSTEM_PROMPT,
                messages=messages,
                tools=agent_tools.TOOL_SCHEMAS,
                max_tokens=MAX_TOKENS,
            )
            for block in response.content:
                if block.type == "text" and block.text:
                    result.steps.append(AgentStep("text", {"text": block.text}))
                    final_text += block.text + "\n"
            result.turns_used += 1
            final_text = final_text.strip()
        except Exception as e:
            agent_logger.log_event("nudge_failed", {"error": str(e)})

    if not final_text:
        final_text = "(no response generated)"

    result.confidence = _extract_confidence(final_text)
    result.text = append_safety_footer(final_text)

    agent_logger.log_event(
        "turn_complete",
        {
            "provider": result.provider,
            "model": result.model,
            "turns": result.turns_used,
            "tools_called": result.tools_called,
            "confidence": result.confidence,
            "refused": result.refused,
        },
    )

    if conversation_history is not None:
        conversation_history.append({"role": "user", "content": user_message})
        conversation_history.append({"role": "assistant", "content": result.text})

    return result


# --- CLI entry point --------------------------------------------------------


def _cli() -> None:
    """Interactive terminal demo. Run with: python agent.py"""
    print("PawPal+ Agent (CLI demo). Type 'quit' to exit.")
    try:
        provider = select_provider()
        print(f"Using provider: {provider.name} ({provider.model})\n")
    except RuntimeError as e:
        print(f"Setup error: {e}")
        return

    owner = Owner(name="Demo Owner", available_minutes=60)
    history: list[dict[str, Any]] = []

    while True:
        try:
            user = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user or user.lower() in {"quit", "exit"}:
            break

        result = run_agent(user, owner, conversation_history=history, provider=provider)
        print(f"\nagent> {result.text}\n")
        if result.tools_called:
            print(f"  [tools used: {', '.join(result.tools_called)}]")
        if result.confidence is not None:
            print(f"  [confidence: {result.confidence:.2f}]")
        print()


if __name__ == "__main__":
    _cli()
