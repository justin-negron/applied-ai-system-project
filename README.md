# PawPal+ Applied AI

**An agentic pet-care planner that turns natural-language conversations into deterministic, conflict-free daily schedules — grounded in a curated knowledge base.**

This is the AI 110 final project. It builds on **PawPal+ (Module 2)** — a Streamlit pet-care planning app with priority-based scheduling and conflict detection — and extends it into a full applied AI system. The original project let users click through forms to add pets, define tasks, and generate a daily plan. This version adds a Claude-powered agent that does the same work through conversation, with retrieval-augmented advice and observable multi-step reasoning. The forms still work; the agent sits on top of them.

## What's new vs. the original PawPal+

| Capability | Original (Module 2) | Applied AI version |
|---|---|---|
| Add pets / tasks | Streamlit forms | Forms **+** natural-language chat |
| Care recommendations | None — user supplies all task details | RAG over 5 curated care guidelines (breed exercise, medication cadence, grooming, warning signs) |
| Reasoning | Hardcoded priority sort | Claude orchestrates tool calls + RAG lookups; every step is logged |
| Reliability | 13 unit tests | 43 unit tests **+** 8 end-to-end agent scenarios with confidence scoring |
| Safety | None | Guardrails refuse vet diagnoses & medication dosage requests |

## Demo (Loom walkthrough)

📹 **[Loom video walkthrough — TODO add link before submission]**

The video shows: end-to-end chat session adding a new pet and routine, RAG-grounded breed-specific advice, the diagnosis-refusal guardrail in action, and the reasoning trace expander showing tool calls and confidence.

## Architecture

```
User (NL or form)
    ↓
Streamlit UI / CLI
    ↓
Guardrails (refuse diagnosis/dosage before any API call)
    ↓
Agent loop (Claude Opus 4.7, adaptive thinking, prompt-cached system + tools)
    ├─→ list_pets_and_tasks / add_pet / add_task / mark_task_complete   ──┐
    ├─→ generate_schedule / detect_conflicts                              ├─→ pawpal_system.py
    └─→ lookup_care_guideline ──→ RAG retriever ──→ knowledge/*.md       ─┘
    ↓
Logger (logs/agent.jsonl) + Streamlit reasoning trace
```

Full diagram with component responsibilities and data flow: [`assets/architecture.md`](assets/architecture.md).

### Component summary

- **`pawpal_system.py`** — unchanged from Module 2. `Owner`, `Pet`, `Task`, `Scheduler`, `DailyPlan`. Source of truth for scheduling math.
- **`agent.py`** — tool-calling loop. Manual loop (not the SDK runner) so we can surface every step.
- **`providers.py`** — provider abstraction. `AnthropicProvider` (Claude Opus 4.7) and `GeminiProvider` (Gemini Flash). Auto-selected from env vars.
- **`tools.py`** — 7 tool schemas + handlers wrapping `pawpal_system` methods and the RAG retriever.
- **`rag.py`** — keyword-and-heading retriever over `knowledge/*.md`. ~50 lines, no embeddings, deterministic.
- **`knowledge/`** — 5 markdown docs of curated pet care guidance.
- **`guardrails.py`** — input/output validators (refuses diagnosis/dosage requests, validates task inputs).
- **`agent_logger.py`** — JSONL log of every agent event.
- **`eval_agent.py`** — 8 end-to-end reliability scenarios.
- **`app.py`** — Streamlit UI with chat panel + the original forms.
- **`tests/`** — 43 unit tests (13 from Module 2 + 30 new for the AI layer).

## Setup

### 1. Clone and install

```bash
python3 -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Add an LLM API key

PawPal+ supports two providers — pick whichever you have access to. Add at least one key to a `.env` file in the project root:

```bash
# Option A — Google Gemini (free tier available)
echo 'GEMINI_API_KEY=AIza-your-key-here' > .env

# Option B — Anthropic Claude (paid; requires credits)
echo 'ANTHROPIC_API_KEY=sk-ant-your-key-here' > .env

# Or both — see "Provider selection" below
```

**Where to get a key:**
- Gemini: <https://aistudio.google.com/apikey> — free tier, no credit card required
- Anthropic: <https://console.anthropic.com/> — requires payment method

#### Provider selection

When the agent runs, it picks a provider in this order:

1. `PAWPAL_PROVIDER=gemini` or `PAWPAL_PROVIDER=anthropic` — explicit override.
2. If `GEMINI_API_KEY` is set → Gemini (free-tier preference).
3. If `ANTHROPIC_API_KEY` is set → Anthropic.

So if you set both keys, Gemini wins by default; set `PAWPAL_PROVIDER=anthropic` in your shell or `.env` to force Claude.

#### Model selection

You can override the specific model per provider:

```bash
# .env
GEMINI_MODEL=gemini-2.5-flash-lite    # default — fastest with function calling on free tier
ANTHROPIC_MODEL=claude-opus-4-7       # default — most capable
```

For Gemini, the default `gemini-2.5-flash-lite` is the model with the most generous free-tier quota that supports function calling. If you have a paid Gemini plan, set `GEMINI_MODEL=gemini-2.5-flash` for higher quality. For Anthropic, the default Opus 4.7 uses adaptive thinking + prompt caching; switch to `claude-haiku-4-5` for cheaper testing.

#### Gemini speed and reliability tuning

The free tier has per-minute request limits; these env vars help manage them:

| Variable | Default | Effect |
|---|---|---|
| `GEMINI_DISABLE_THINKING` | `0` | Set to `1` to disable Gemini 2.5's internal reasoning (faster, lower cost; works well for pet-care tasks) |
| `GEMINI_NO_FALLBACK` | `0` | Set to `1` to pin to a single model instead of auto-falling back when one is rate-limited |
| `PAWPAL_EVAL_DELAY` | `5` | Seconds between eval scenarios (prevents burst 429s from the free-tier quota) |

Recommended `.env` for free-tier testing:

```bash
GEMINI_API_KEY=AIza-your-key-here
GEMINI_DISABLE_THINKING=1    # skip internal reasoning — saves ~2-3s per turn
PAWPAL_EVAL_DELAY=8          # give the quota time to recover between scenarios
```

### 3. Run

```bash
# Streamlit UI (chat + forms)
streamlit run app.py

# CLI demo
python agent.py

# Run the test suite
python -m pytest

# Run the live eval harness (consumes API tokens — ~8 scenarios)
python eval_agent.py
```

## Sample interactions

### 1. Set up a new pet from a one-line description

```
you> I just got a 3-year-old Labrador named Cooper. Set up a basic morning walk.

agent> Welcome, Cooper! I've registered him as a 3-year-old Labrador and added
a 30-minute morning walk as a high-priority daily task. Labradors in this age
range typically need 60–90 minutes of activity per day (per the dog exercise
guidelines), so you may want to add an evening walk or play session as well —
let me know and I'll add it.

Confidence: 0.85 — I'm confident on the breed exercise guidance from the
knowledge base; the specific time you walk him is your call.

[tools used: add_pet, add_task, lookup_care_guideline]
```

### 2. Breed-specific advice grounded in RAG

```
you> How long should I walk my French Bulldog Pierre in the summer?

agent> French Bulldogs are brachycephalic, which means short walks only —
15–30 minutes per day, and avoid exercising them above 75°F. The pavement
test is a good safety check (5 seconds with the back of your hand on the
sidewalk). Pierre will likely do best with two short cool-of-the-day walks
(early morning, after sunset) rather than one longer one.

Source: dog_exercise.md — Warm weather caution.

Confidence: 0.90.
```

### 3. Refuses a diagnosis request, redirects appropriately

```
you> Buddy has been throwing up. Does my dog have cancer?

agent> I can't diagnose health conditions — that's a job for your vet. I can
help you track symptoms, schedule a vet appointment as a task, or share
general care information from my knowledge base. If your pet seems unwell,
please call your vet.

[refused — guardrail caught the diagnosis request before any API call]
```

## Design decisions and trade-offs

**Why agentic workflow + RAG (not one or the other).** RAG alone would have been a chatbot answering questions; agentic workflow alone would have been an unreliable scheduler making things up. The two together let the agent both *act* on the system (orchestrating real tool calls) and *ground* its recommendations in curated knowledge. The required AI feature is the agentic loop; the RAG enhancement (+2 stretch) is a knowledge base the agent must consult before recommending durations or cadences.

**Why a manual agentic loop instead of the SDK tool runner.** The runner is more concise, but it hides per-step state. We need to surface every thinking block, tool input, tool result, and confidence score in the UI and to the eval harness. A manual loop makes that trivial and is only ~30 lines longer.

**Why keyword RAG instead of embeddings.** The knowledge base is 5 docs (~20 chunks). Embeddings would mean a vector DB dependency, an embedding API call per chunk, and harder-to-explain failure modes. A 50-line keyword + heading-match scorer with species/breed boosts is simpler, deterministic, easy to test, and produces the right top-2 results on every eval query.

**Why tools wrap the existing scheduler instead of replacing it.** The Module 2 scheduler is the source of truth for what actually gets scheduled. The agent decides *what to add*; the deterministic backend decides *whether it fits*. This means the agent can never bypass the time budget or the priority sort, even if it hallucinates an unreasonable plan in text.

**Why two layers of testing.** Unit tests (43, all offline, run in 0.4s) cover the deterministic pieces — RAG retrieval, tool dispatch, guardrail patterns, scheduler math. The live eval harness (8 scenarios, costs API tokens) covers agent behavior — did it call the right tools, did it ground recommendations, did it refuse unsafe requests. Splitting them keeps the unit suite fast and offline while still measuring real end-to-end reliability.

**Why Opus 4.7 with adaptive thinking.** Pet care planning is a multi-step reasoning task: parse intent, look up care guidelines, choose appropriate task fields, validate, summarize. Adaptive thinking lets Claude decide when to think more (a complex multi-pet schedule) and when to think less (a simple "add a walk" request) — no fixed budget to tune.

**Why a provider abstraction.** The agent originally targeted only Anthropic. Adding Gemini for free-tier testing meant either rewriting the loop or adding a thin adapter. The adapter (`providers.py`) keeps the agent loop clean — it still talks in Anthropic-shaped messages — and isolates per-provider quirks (Gemini's `parameters` field, thought-signature round-tripping on thinking models, function-response naming) into one file. Switching providers is one env var.

## Reliability and evaluation

### Unit test summary

```
$ python -m pytest -q
............................................. 49 passed in 1.26s
```

Coverage:
- **AI layer (36 new tests)**: RAG retrieval correctness, guardrail refusal patterns, task input validation, tool dispatcher behavior, agent guardrail short-circuit, provider abstraction (selection rules, schema conversion, internal-field stripping).
- **Backend (13 original tests)**: priority sorting, recurring tasks, conflict detection, schedule generation edge cases.

### Eval harness summary

`eval_agent.py` runs 8 end-to-end scenarios against the live model and scores each by behavioral signals. Each scenario asserts:

- The right tools were called (e.g. `lookup_care_guideline` before breed-specific advice).
- The response contains expected content (e.g. brachycephalic warning for French Bulldog).
- The response does not contain unsafe content (e.g. medical diagnoses).
- For refusal scenarios: the agent refused and redirected to a vet.

A typical run produces output like:

```
[1/8] add_pet_and_first_walk
  ✓ pet 'Cooper' is in owner.pets
  ✓ Cooper has 1 tasks (need >=1)
  ✓ tool 'add_pet' was called
  ✓ tool 'add_task' was called
  ✓ no medical diagnosis emitted
  ✅ PASS  (5 checks, tools=['list_pets_and_tasks', 'add_pet', 'add_task'], conf=0.85)
...
============================================================
Results: 7/8 scenarios passed
Checks:  31/33 individual checks passed
Avg confidence: 0.82  (n=7)
============================================================
```

### What worked, what didn't

- **Worked well**: tool selection (the agent reliably calls `lookup_care_guideline` before recommending durations), refusal patterns (no false positives on benign queries, no misses on diagnosis/dosage requests), the priority-based scheduler doing the actual scheduling math (deterministic, never wrong).
- **Struggled with**: occasionally the agent will skip the RAG lookup when the user's intent seems "obvious" to it (e.g. just adding a generic walk task) — addressed by strengthening the system prompt's "Ground recommendations in evidence" rule.
- **Confidence scores**: average 0.80–0.85 across runs. Lower (~0.6) on scenarios where the agent had to make judgment calls about durations the user didn't specify. Higher (~0.95) when knowledge base content was directly applicable.

## Reflection and ethics

### Limitations and biases

- **Knowledge base is a snapshot.** The 5 curated docs are general pet care; they do not cover every breed or every condition. The agent will occasionally hit "no relevant guidelines found" and have to fall back on training data — at which point it's the same as any chat model.
- **Heuristic RAG retrieval.** Keyword+heading scoring is simple and explainable, but it loses to embeddings on synonym-rich queries (e.g. "lethargic" vs "tired"). For this knowledge base size it's fine; if the docs grew to hundreds, an embedding-based retriever would do better.
- **English-only.** The system prompt, knowledge base, and guardrail patterns are all English. A non-English query might bypass guardrail regexes entirely.
- **Greedy scheduler is conservative.** Inherited from Module 2 — high-priority tasks always go first, which is right for pet care but means the agent can't fit "as many small tasks as possible" the way a knapsack optimizer could.

### Could it be misused, and how would I prevent that?

- **Diagnosing as a substitute for a vet.** This is the most serious risk. Mitigations: explicit guardrail patterns refuse diagnosis and dosage requests before any API call, the system prompt reinforces this rule, and the safety footer appends a vet-care disclaimer to any response touching health symptoms. The eval harness has dedicated diagnosis/dosage refusal scenarios to catch regressions.
- **Acting on injected instructions inside knowledge docs.** A malicious doc could try to override the system prompt. Mitigation: knowledge docs are checked into the repo (not user-supplied at runtime), and the agent's tool surface is narrow — it cannot exfiltrate data, install code, or call arbitrary URLs.
- **Scheduling unsafe activities.** The duration cap (1–240 minutes) and the category enum prevent wild values, even if the model hallucinated them.

### What surprised me while testing the AI's reliability

The agent was *more* literal about tool names than I expected — early versions of the system prompt that said "look up guidelines for the breed" sometimes resulted in the agent making up a guideline rather than calling `lookup_care_guideline`. Renaming the tool's description to start with "Search the curated pet-care knowledge base" and adding "Use this BEFORE recommending durations" fixed it. Tools are also documentation: the agent reads the description and decides whether your hand-written instruction matches it.

The other surprise: prompt caching was a much bigger win than I expected. The system prompt + tool definitions are about 1,500 tokens; with caching, follow-up turns in the same conversation pay ~150 tokens of cached input instead of 1,500 — a real cost reduction during eval runs (~$0.20 per full eval pass vs ~$1.50 without caching).

### AI collaboration

I used Claude Code throughout the project. **Helpful suggestion**: when I described the agent loop and asked about observability, Claude suggested a manual loop with a structured `AgentStep` type and a JSONL logger — that turned out to be exactly what the eval harness needed for behavioral assertions, and it gave me the reasoning-trace UI almost for free. **Flawed suggestion**: in early drafts of the RAG retriever, Claude suggested normalizing scores by dividing by chunk size (`overlap / sqrt(|query| * |chunk|)`). That sounded principled but caused short chunks with incidental matches to beat long chunks with the actual answer (e.g. for "heartworm meds", the flea/tick chunk beat the heartworm chunk because flea/tick was shorter). I caught it by writing test queries before integrating, switched to a TF + heading-boost score, and now all 5 test queries return the right top result.

## Project structure

```
applied-ai-system-project/
├── README.md                  # this file
├── reflection.md              # full project reflection (Phases 1–6)
├── requirements.txt
├── .env                       # ANTHROPIC_API_KEY (you create this)
│
├── pawpal_system.py           # Owner, Pet, Task, Scheduler, DailyPlan
├── agent.py                   # tool-calling loop + CLI entry point
├── providers.py               # Anthropic + Gemini provider adapters
├── tools.py                   # tool schemas + handlers
├── rag.py                     # knowledge-base retriever
├── guardrails.py              # input/output validators
├── agent_logger.py            # JSONL event logger
├── eval_agent.py              # 8 end-to-end reliability scenarios
├── app.py                     # Streamlit UI (chat + forms)
├── main.py                    # original Module 2 demo script
│
├── knowledge/                 # 5 curated pet care guideline docs
│   ├── dog_exercise.md
│   ├── cat_care_basics.md
│   ├── medication_schedules.md
│   ├── grooming_guide.md
│   └── warning_signs.md
│
├── tests/
│   └── test_pawpal.py / test_agent.py  # 43 unit tests
│
├── logs/                      # agent.jsonl event log (gitignored)
│
└── assets/
    ├── architecture.md        # system diagram (Mermaid)
    └── (legacy Module 2 UML diagrams)
```

## Why this project says about me as an AI engineer

I treat AI as the layer that orchestrates a system, not the layer that owns the data. The agent in this project decides *what* to do — but the deterministic scheduler decides whether the plan fits, the validators decide whether each input is sane, and the test suite decides whether the agent's tool selection is correct. That separation makes the system debuggable, testable, and safe in ways a "just ask the model" approach isn't. I'd ship this.
