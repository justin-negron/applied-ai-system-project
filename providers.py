"""LLM provider abstraction for the PawPal+ agent.

Supports two backends:
- AnthropicProvider — claude-opus-4-7 (paid; uses adaptive thinking + prompt
  caching).
- GeminiProvider — gemini-2.0-flash (Google free tier; cheaper for testing).

Selection rules (in order of precedence):
1. PAWPAL_PROVIDER env var ('anthropic' | 'gemini').
2. If GEMINI_API_KEY is set → Gemini (free-tier preference).
3. If ANTHROPIC_API_KEY is set → Anthropic.
4. Otherwise raise — no provider available.

Internally the agent always uses an Anthropic-shaped message list. Each
provider converts to its native format on the way out and back.
"""

from dataclasses import dataclass, field
import os
import random
import threading
import time
from typing import Any, Optional


# --- Normalized response shape ----------------------------------------------


@dataclass
class TextBlock:
    text: str
    type: str = "text"


@dataclass
class ThinkingBlock:
    thinking: str
    type: str = "thinking"


@dataclass
class ToolUseBlock:
    id: str
    name: str
    input: dict
    type: str = "tool_use"


@dataclass
class ProviderResponse:
    content: list = field(default_factory=list)  # TextBlock | ThinkingBlock | ToolUseBlock
    stop_reason: str = "end_turn"  # "end_turn" | "tool_use"
    provider: str = ""
    model: str = ""
    raw: Any = None  # Provider-native content (preserves Gemini thought_signatures, etc.)

    def to_message_content(self) -> list[dict]:
        """Serialize this response into the dict shape we keep in the message
        history. Thinking blocks are dropped — they don't need to be replayed
        and aren't accepted in messages on every provider."""
        out: list[dict] = []
        for b in self.content:
            if b.type == "text":
                out.append({"type": "text", "text": b.text})
            elif b.type == "tool_use":
                out.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
        return out


# --- Base provider ----------------------------------------------------------


class Provider:
    name: str = ""
    model: str = ""

    def call(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict],
        max_tokens: int,
    ) -> ProviderResponse:
        raise NotImplementedError


# --- Anthropic --------------------------------------------------------------


class AnthropicProvider(Provider):
    name = "anthropic"

    # Free-tier hard limits. Override with env vars if you have a paid plan.
    _RPM_LIMIT = int(os.getenv("ANTHROPIC_RPM_LIMIT", "5"))
    _WINDOW = 60.0  # seconds

    def __init__(self) -> None:
        import anthropic

        if not os.getenv("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY is not set.")
        self._anthropic = anthropic
        self.client = anthropic.Anthropic()
        self.model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
        # Sliding-window rate-limiter state (shared across all calls on this instance).
        self._req_times: list[float] = []
        self._rate_lock = threading.Lock()

    def _rate_limit_wait(self) -> None:
        """Block until a request slot is available under the RPM cap.

        Uses a sliding 60-second window: counts requests in the last 60s and
        sleeps until the oldest one falls out if we're at the limit.
        """
        while True:
            now = time.monotonic()
            with self._rate_lock:
                self._req_times = [t for t in self._req_times if now - t < self._WINDOW]
                if len(self._req_times) < self._RPM_LIMIT:
                    self._req_times.append(now)
                    return
                # Sleep until the oldest request's slot expires, plus a small buffer.
                wait_for = self._WINDOW - (now - self._req_times[0]) + 0.5
            print(f"  [rate limit] {len(self._req_times)}/{self._RPM_LIMIT} RPM — waiting {wait_for:.1f}s…")
            time.sleep(wait_for)

    def _strip_internal_fields(self, messages: list[dict]) -> list[dict]:
        """Remove keys we use for cross-provider bookkeeping (prefixed with _)."""
        cleaned = []
        for msg in messages:
            content = msg["content"]
            if isinstance(content, list):
                new_content = []
                for block in content:
                    if isinstance(block, dict):
                        new_content.append({k: v for k, v in block.items() if not k.startswith("_")})
                    else:
                        new_content.append(block)
                cleaned.append({"role": msg["role"], "content": new_content})
            else:
                cleaned.append(msg)
        return cleaned

    # Models that support extended thinking (adaptive mode).
    _THINKING_MODELS = {"claude-opus-4-7", "claude-sonnet-4-6"}

    def call(self, system, messages, tools, max_tokens):
        self._rate_limit_wait()
        clean_messages = self._strip_internal_fields(messages)
        kwargs: dict = dict(
            model=self.model,
            max_tokens=max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            tools=tools,
            messages=clean_messages,
        )
        # Adaptive thinking is only available on Opus and Sonnet; skip for Haiku.
        if any(m in self.model for m in self._THINKING_MODELS):
            kwargs["thinking"] = {"type": "adaptive"}
        response = self.client.messages.create(**kwargs)

        blocks = []
        for b in response.content:
            if b.type == "text" and b.text:
                blocks.append(TextBlock(text=b.text))
            elif b.type == "thinking" and getattr(b, "thinking", ""):
                blocks.append(ThinkingBlock(thinking=b.thinking))
            elif b.type == "tool_use":
                blocks.append(ToolUseBlock(id=b.id, name=b.name, input=b.input))

        stop = "tool_use" if response.stop_reason == "tool_use" else "end_turn"
        return ProviderResponse(content=blocks, stop_reason=stop, provider=self.name, model=self.model)


# --- Gemini -----------------------------------------------------------------


class GeminiProvider(Provider):
    name = "gemini"

    # Ordered fallback list for the free tier. If the primary model is in an
    # outage / rate-limited / capacity-exhausted, the provider walks the list
    # and uses the first model that succeeds. Each one supports function
    # calling. Ordered roughly by quality desc / availability asc.
    _DEFAULT_FALLBACK_MODELS = (
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash",
        "gemini-flash-lite-latest",
        "gemini-flash-latest",
    )

    def __init__(self) -> None:
        from google import genai
        from google.genai import types

        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set.")
        self._genai = genai
        self._types = types
        self.client = genai.Client(api_key=api_key)

        # Primary model: env var, else first entry in the fallback list.
        primary = os.getenv("GEMINI_MODEL") or self._DEFAULT_FALLBACK_MODELS[0]
        # The active model can change at runtime via fallback. `self.model`
        # always reflects the model that produced the most recent response.
        self.model = primary
        self._primary_model = primary

        # Build the fallback chain, putting the primary first and removing
        # duplicates while preserving order.
        chain: list[str] = [primary]
        for m in self._DEFAULT_FALLBACK_MODELS:
            if m not in chain:
                chain.append(m)
        # Allow opt-out for users who want a hard pin to a single model.
        if os.getenv("GEMINI_NO_FALLBACK", "").lower() in {"1", "true", "yes"}:
            chain = [primary]
        self._model_chain = chain

        # Gemini 2.5 models reason internally before responding. That's good
        # for hard problems but adds latency on free-tier infrastructure.
        # Setting GEMINI_DISABLE_THINKING=1 sets thinking_budget=0 in the
        # request, which disables internal reasoning. Pet-care planning is
        # mostly look-up + structured tool calls, so this is usually fine.
        self._disable_thinking = os.getenv("GEMINI_DISABLE_THINKING", "").lower() in {"1", "true", "yes"}

    def _convert_tools(self, tools: list[dict]):
        """Anthropic tool schemas → Gemini function declarations."""
        declarations = []
        for t in tools:
            schema = dict(t.get("input_schema", {"type": "object"}))
            # Gemini wants a parameters object even for no-arg tools.
            if schema.get("type") == "object" and not schema.get("properties"):
                schema = {"type": "object", "properties": {}}
            declarations.append(
                {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": schema,
                }
            )
        return [self._types.Tool(function_declarations=declarations)]

    def _convert_messages(self, messages: list[dict]) -> list:
        """Anthropic-shaped messages → Gemini Content list."""
        types = self._types
        contents = []

        for msg in messages:
            gemini_role = "user" if msg["role"] == "user" else "model"
            content = msg["content"]

            # If the assistant turn carries the original Gemini Content
            # (preserving thought_signatures), use it directly. This is what
            # newer thinking models require for function-calling round-trips.
            raw = msg.get("_gemini_content")
            if raw is not None and gemini_role == "model":
                contents.append(raw)
                continue

            if isinstance(content, str):
                contents.append(types.Content(role=gemini_role, parts=[types.Part(text=content)]))
                continue

            parts = []
            for block in content:
                btype = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
                if btype == "text":
                    text = block["text"] if isinstance(block, dict) else block.text
                    if text:
                        parts.append(types.Part(text=text))
                elif btype == "tool_use":
                    name = block["name"]
                    args = block["input"]
                    fc_id = block.get("id")
                    parts.append(
                        types.Part(
                            function_call=types.FunctionCall(name=name, args=args, id=fc_id)
                        )
                    )
                elif btype == "tool_result":
                    tool_name = block.get("_tool_name", "unknown_tool")
                    raw = block.get("content", "")
                    is_error = bool(block.get("is_error"))
                    response_dict = {"error" if is_error else "result": raw}
                    # Older SDK versions don't accept `id` here — Gemini
                    # matches responses to calls by name + position.
                    parts.append(
                        types.Part.from_function_response(
                            name=tool_name,
                            response=response_dict,
                        )
                    )
            if parts:
                contents.append(types.Content(role=gemini_role, parts=parts))

        return contents

    # HTTP status codes worth retrying. 429 = rate limit (the API tells us how
    # long to wait via retryDelay in details); 5xx = transient server error.
    _RETRYABLE_CODES = {429, 500, 502, 503, 504}
    _MAX_RETRIES = 4
    _BASE_DELAY = 2.0  # seconds

    def _generate_with_retry(self, contents, config):
        """Call the Gemini API with exponential-backoff retry on transient
        errors, then fall back to the next model in the chain if the current
        one stays unavailable. The google-genai SDK does not retry 5xx by
        default, and free-tier models can return 503 / 429 for minutes at a
        time during demand spikes — so we handle both retry and fallback here.
        """
        from google.genai import errors

        last_error: Optional[Exception] = None

        for model_name in self._model_chain:
            for attempt in range(self._MAX_RETRIES):
                try:
                    response = self.client.models.generate_content(
                        model=model_name,
                        contents=contents,
                        config=config,
                    )
                    # Update the active model so callers and logs reflect what
                    # actually answered (especially after fallback).
                    self.model = model_name
                    return response
                except errors.APIError as e:
                    last_error = e
                    if e.code not in self._RETRYABLE_CODES:
                        raise

                    # Last attempt on this model — break out and try the next.
                    if attempt + 1 >= self._MAX_RETRIES:
                        break

                    delay = self._extract_retry_delay(e) or self._backoff_delay(attempt)
                    time.sleep(delay)

        # All models exhausted.
        raise last_error  # type: ignore[misc]

    def _backoff_delay(self, attempt: int) -> float:
        """Exponential backoff with full jitter."""
        cap = 30.0
        return min(cap, self._BASE_DELAY * (2 ** attempt)) * (0.5 + random.random() / 2)

    def _extract_retry_delay(self, err) -> Optional[float]:
        """Pull retryDelay from a 429 RetryInfo block if present."""
        details = getattr(err, "details", None)
        if not isinstance(details, dict):
            return None
        for entry in details.get("error", {}).get("details", []) or []:
            if "RetryInfo" in entry.get("@type", ""):
                raw = entry.get("retryDelay", "")
                # Format is "Ns" or "N.Ns".
                if isinstance(raw, str) and raw.endswith("s"):
                    try:
                        return float(raw[:-1])
                    except ValueError:
                        pass
        return None

    def call(self, system, messages, tools, max_tokens):
        types = self._types

        config_kwargs: dict[str, Any] = dict(
            system_instruction=system,
            tools=self._convert_tools(tools),
            max_output_tokens=max_tokens,
        )
        if self._disable_thinking:
            config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)

        config = types.GenerateContentConfig(**config_kwargs)

        response = self._generate_with_retry(
            contents=self._convert_messages(messages),
            config=config,
        )

        blocks = []
        has_tool_call = False

        if response.candidates and response.candidates[0].content:
            for part in response.candidates[0].content.parts or []:
                if getattr(part, "text", None):
                    blocks.append(TextBlock(text=part.text))
                fc = getattr(part, "function_call", None)
                if fc and getattr(fc, "name", None):
                    has_tool_call = True
                    # Generate an ID if Gemini didn't provide one (older models).
                    fc_id = getattr(fc, "id", None) or f"gemcall_{len(blocks)}"
                    args = dict(fc.args) if fc.args else {}
                    blocks.append(ToolUseBlock(id=fc_id, name=fc.name, input=args))

        stop = "tool_use" if has_tool_call else "end_turn"
        raw_content = response.candidates[0].content if response.candidates else None
        return ProviderResponse(
            content=blocks,
            stop_reason=stop,
            provider=self.name,
            model=self.model,
            raw=raw_content,
        )


# --- Selection --------------------------------------------------------------


def select_provider(override: Optional[str] = None) -> Provider:
    """Pick a provider based on env vars (or explicit override)."""
    choice = (override or os.getenv("PAWPAL_PROVIDER") or "").lower().strip()

    if choice == "anthropic":
        return AnthropicProvider()
    if choice == "gemini":
        return GeminiProvider()

    # Auto-select: prefer Gemini (free tier) when both keys are present.
    if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
        return GeminiProvider()
    if os.getenv("ANTHROPIC_API_KEY"):
        return AnthropicProvider()

    raise RuntimeError(
        "No LLM provider available. Set GEMINI_API_KEY (free tier) or "
        "ANTHROPIC_API_KEY in your .env file. To force a specific provider, "
        "set PAWPAL_PROVIDER=anthropic or PAWPAL_PROVIDER=gemini."
    )
