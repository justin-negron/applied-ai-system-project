# PawPal AI Pro

**An agentic pet-hotel management system that turns natural-language conversations into conflict-free daily schedules — assigning tasks across employees, grounded in a curated pet-care knowledge base.**

This is the AI 110 final project. It builds on **PawPal+ (Module 2)** — a Streamlit pet-care planning app with priority-based scheduling and conflict detection — and extends it into a full applied AI system for running a pet hotel or dog lodge. The original project let a single owner click through forms to manage their own pets. This version adds a Claude-powered agent, multi-employee scheduling, and a full admin dashboard.

## What's new vs. the original PawPal+

| Capability | Original (Module 2) | Applied AI version |
|---|---|---|
| User model | Single owner | Admin + named employees with individual time budgets |
| Add pets / tasks | Streamlit forms | Forms **+** natural-language chat agent |
| Schedule generation | One plan for the owner | Assign tasks across employees; Quick (instant) or AI (agent-reasoned) |
| Care recommendations | None | RAG over 5 curated care guidelines (breed exercise, meds, grooming, warning signs) |
| Reasoning | Hardcoded priority sort | Claude orchestrates tool calls + RAG lookups; every step is logged |
| Reliability | 13 unit tests | 49 unit tests + 8 end-to-end agent scenarios with confidence scoring |
| Safety | None | Guardrails refuse vet diagnoses & medication dosage requests |

## Demo

📹 **[Loom video walkthrough](https://www.loom.com/share/b302a9f8a7b84df187060855da15d9d3)**

The video shows: loading the pet hotel demo (8 dogs, 3 employees), running the AI schedule, breed-specific RAG advice, and the diagnosis-refusal guardrail in action.

## Architecture

```
Admin (browser or CLI)
    ↓
Streamlit UI
    ↓
Guardrails (refuse diagnosis/dosage before any API call)
    ↓
Agent loop (Claude Sonnet 4.6, adaptive thinking, prompt-cached system + tools)
    ├─→ list_pets_and_tasks / add_pet / add_task / mark_task_complete  ──┐
    ├─→ list_employees / add_employee / assign_tasks_to_employees        ├─→ pawpal_system.py
    ├─→ generate_schedule / detect_conflicts                             ─┘
    └─→ lookup_care_guideline ──→ RAG retriever ──→ knowledge/*.md
    ↓
Logger (logs/agent.jsonl) + Streamlit reasoning trace
```

Full diagram: [`assets/architecture.md`](assets/architecture.md)

### Component summary

- **`pawpal_system.py`** — core data model. `Owner` (admin), `Employee` (name + available minutes + assigned tasks), `Pet`, `Task`, `Scheduler`, `DailyPlan`. `Owner.assign_tasks_to_employees()` runs the greedy load-balancing algorithm.
- **`agent.py`** — manual tool-calling loop (not the SDK runner) with per-step observability, confidence scoring, rate limiting, and an empty-response recovery nudge.
- **`providers.py`** — provider abstraction. `AnthropicProvider` (Claude Sonnet 4.6, adaptive thinking, prompt caching, 5 RPM rate limiter) and `GeminiProvider` (Gemini Flash, retry-with-backoff, model fallback chain). Auto-selected from env vars.
- **`tools.py`** — 10 tool schemas + handlers: pet CRUD, task CRUD, employee CRUD, schedule generation, conflict detection, RAG lookup.
- **`rag.py`** — keyword + TF retriever over `knowledge/*.md` with species/breed boost. ~50 lines, no embeddings, deterministic.
- **`knowledge/`** — 5 curated pet care guideline docs.
- **`guardrails.py`** — input/output validators (refuses diagnosis/dosage requests, validates task fields).
- **`agent_logger.py`** — JSONL log of every agent event.
- **`eval_agent.py`** — 8 end-to-end reliability scenarios with inter-scenario delay to avoid free-tier rate limits.
- **`app.py`** — Streamlit UI. Sections: Admin Setup → Chat → Employees → Dogs → Tasks → Generate Schedule.

## UI walkthrough

The app is organized top-to-bottom in the order you'd use it:

1. **Admin Setup** — enter your name to log in. Hit **🐾 Load Pet Hotel Demo** to instantly seed 3 employees and 8 dogs with breed-accurate tasks.
2. **Chat with Agent** — natural-language interface. Ask the agent to add dogs, look up breed care, or build a schedule.
3. **👥 Employees** — add staff by name and hours. Live table shows available/assigned/remaining time.
4. **🐕 Dogs** — add dogs with species, breed, and age.
5. **📝 Tasks** — assign tasks to dogs. Only today's due tasks are shown; completed daily tasks create tomorrow's occurrence automatically.
6. **📋 Generate Today's Schedule** — two modes:
   - **⚡ Quick Schedule** — deterministic priority-based assignment, instant, no API call.
   - **✨ AI Schedule** — agent reviews all dogs, tasks, priorities, and employee schedules; explains its reasoning; shows per-employee task tables and anything that couldn't fit.

## Setup

### 1. Clone and install

```bash
python3 -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Add an API key

```bash
# Option A — Anthropic Claude (recommended)
echo 'ANTHROPIC_API_KEY=sk-ant-your-key-here' >> .env
echo 'PAWPAL_PROVIDER=anthropic' >> .env

# Option B — Google Gemini (free tier available)
echo 'GEMINI_API_KEY=AIza-your-key-here' >> .env
```

**Where to get a key:**
- Anthropic: <https://console.anthropic.com/> — requires payment method
- Gemini: <https://aistudio.google.com/apikey> — free tier, no credit card required

#### Provider selection

```
PAWPAL_PROVIDER=anthropic|gemini  →  explicit override (highest priority)
GEMINI_API_KEY set                →  Gemini (free-tier default)
ANTHROPIC_API_KEY set             →  Anthropic
```

#### Model selection

```bash
# .env
ANTHROPIC_MODEL=claude-sonnet-4-6   # default — adaptive thinking, $3/$15 per MTok
GEMINI_MODEL=gemini-2.5-flash-lite  # default — free tier with function calling
```

Anthropic model cost guide (prompt caching reduces input cost ~10×):

| Model | Input | Output | Good for |
|---|---|---|---|
| `claude-sonnet-4-6` | $3/MTok | $15/MTok | **Default** — high accuracy, affordable |
| `claude-opus-4-7` | $15/MTok | $75/MTok | Maximum reasoning |
| `claude-haiku-4-5-20251001` | $0.80/MTok | $4/MTok | Budget testing |

#### Gemini tuning

| Variable | Default | Effect |
|---|---|---|
| `GEMINI_DISABLE_THINKING` | `0` | `1` = disable internal reasoning (faster, cheaper) |
| `GEMINI_NO_FALLBACK` | `0` | `1` = pin to a single model, no auto-fallback |
| `PAWPAL_EVAL_DELAY` | `5` | Seconds between eval scenarios (prevents burst 429s) |

### 3. Run

```bash
# Streamlit UI
streamlit run app.py --server.headless true   # WSL/headless: open localhost:8501 manually

# CLI agent
python agent.py

# Unit tests (offline, ~1s)
python -m pytest

# Live eval harness (~8 API calls per scenario)
python eval_agent.py
```

## Sample interactions

### 1. Employee scheduling via chat

```
you> Add Jacob for 4 hours, Sierra and Noah for 6 hours each.
     We have Bella (Golden Retriever, 3yr) with a morning walk and feeding.
     Assign the work.

agent> Added 3 employees. Assigned Bella's Morning Walk (30min, high) to Jacob
and Morning Feeding (10min, high) to Sierra. Noah has remaining capacity.

Confidence: 0.92 — all tasks fit within available time with no conflicts.

[tools used: add_employee ×3, add_pet, add_task ×2, assign_tasks_to_employees]
```

### 2. Breed-specific advice grounded in RAG

```
you> How long should I walk Coco, my French Bulldog, in the summer?

agent> French Bulldogs are brachycephalic — limit walks to 15–30 minutes and
avoid exercise above 75°F. Two short cool-of-the-day walks (early morning,
after sunset) are better than one long one.

Source: dog_exercise.md — Warm weather caution.

Confidence: 0.90.
```

### 3. Refuses a diagnosis request

```
you> Buddy has been throwing up. Does my dog have cancer?

agent> I can't diagnose health conditions — please call your vet. I can help
you schedule a vet appointment as a task.

[refused — guardrail triggered before any API call]
```

## Design decisions and trade-offs

**Why employee scheduling instead of a single-owner model.** A pet hotel has staff with different shift lengths. The original Module 2 scheduler had one `available_minutes` budget. The new `Employee` model gives each staff member their own budget; `assign_tasks_to_employees()` uses a greedy least-loaded-first algorithm (highest priority task → employee with least time used who can still fit it), which distributes work evenly rather than filling the most-available employee first.

**Why two schedule modes.** The Quick Schedule is deterministic, instant, and costs nothing — useful for a fast daily sanity check. The AI Schedule is slower and costs API tokens but explains its reasoning and can factor in nuance the algorithm can't (e.g. "keep Coco's walk short because it's hot today"). Giving both lets the admin choose based on urgency and budget.

**Why a manual agentic loop instead of the SDK tool runner.** The runner hides per-step state. We need to surface every thinking block, tool input, tool result, and confidence score in the UI and eval harness. A manual loop makes that trivial.

**Why keyword RAG instead of embeddings.** The knowledge base is 5 docs (~20 chunks). Embeddings would add a vector DB, an embedding API call per chunk, and harder-to-explain failures. A 50-line keyword + heading-match scorer with species/breed boosts is simpler, deterministic, easy to test, and returns the right top-2 result on every eval query.

**Why Sonnet 4.6 instead of Opus 4.7.** Sonnet 4.6 is 5× cheaper ($3 vs $15/MTok input) and supports adaptive thinking. For pet-care planning — mostly structured tool calls with occasional reasoning — Sonnet performs as well as Opus at a fraction of the cost. Opus is available via `ANTHROPIC_MODEL=claude-opus-4-7`.

**Why a provider abstraction.** The agent loop always speaks Anthropic-shaped messages. Each provider converts to its native format on the way out and back, isolating per-provider quirks (Gemini's `parameters` field, thought-signature round-tripping on 2.5 thinking models, function-response naming) into one file. Switching providers is one env var.

## Reliability and evaluation

### Unit test summary

```
$ python -m pytest -q
................................................. 49 passed in 1.1s
```

Coverage:
- **AI layer (36 tests)**: RAG retrieval correctness, guardrail refusal patterns, task validation, tool dispatch, agent guardrail short-circuit, provider abstraction (selection rules, schema conversion, field stripping).
- **Backend (13 original tests)**: priority sorting, recurring tasks, conflict detection, schedule generation edge cases.

### Eval harness

`eval_agent.py` runs 8 live scenarios and scores each by behavioral signals:

| Scenario | What it checks |
|---|---|
| `add_pet_and_first_walk` | Adds pet + task, no diagnosis |
| `breed_specific_advice` | Calls RAG, cites source |
| `schedule_with_existing_tasks` | Generates schedule correctly |
| `conflict_detection` | Surfaces time overruns |
| `diagnosis_refusal` | Refuses, redirects to vet |
| `dosage_refusal` | Refuses medication dosage |
| `brachycephalic_warning` | RAG flags heat risk for French Bulldog |
| `cat_routine_setup` | Adds multiple tasks for a cat |

A typical run costs **$0.10–0.20** (Sonnet 4.6, prompt caching) and takes ~3 minutes due to the 5 RPM rate limit on the Anthropic free tier.

## Project structure

```
applied-ai-system-project/
├── README.md
├── reflection.md
├── requirements.txt
├── .env                       # API keys (you create this)
├── demo_prompt.txt            # copy-paste prompt for bulk pet hotel setup
│
├── pawpal_system.py           # Owner, Employee, Pet, Task, Scheduler, DailyPlan
├── agent.py                   # tool-calling loop + CLI entry point
├── providers.py               # Anthropic + Gemini provider adapters
├── tools.py                   # 10 tool schemas + handlers
├── rag.py                     # knowledge-base retriever
├── guardrails.py              # input/output validators
├── agent_logger.py            # JSONL event logger
├── eval_agent.py              # 8 end-to-end reliability scenarios
├── app.py                     # Streamlit UI
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
│   ├── test_pawpal.py         # 13 original backend tests
│   └── test_agent.py         # 36 AI layer tests
│
├── logs/                      # agent.jsonl (gitignored)
│
└── assets/
    └── architecture.md        # system diagram (Mermaid)
```

## Reflection and ethics

### Limitations

- **Knowledge base is a snapshot.** 5 docs covering general pet care. The agent falls back on model training data when the knowledge base has no match — at that point it behaves like any chat model.
- **Heuristic RAG.** Keyword + heading scoring loses to embeddings on synonym-rich queries. Fine for 5 docs; would need an embedding-based retriever for hundreds.
- **English-only.** System prompt, knowledge base, and guardrail regexes are English. Non-English queries may bypass guardrails.
- **Greedy employee assignment.** Least-loaded-first is fair but not optimal — a knapsack solver could pack more tasks into a shift. Good enough for pet hotel scale.

### Misuse risks and mitigations

- **Diagnosing as a substitute for a vet.** Guardrail patterns block diagnosis requests before any API call; the system prompt reinforces the rule; the safety footer adds a vet disclaimer to any health-adjacent response. Eval harness has dedicated refusal scenarios.
- **Prompt injection via knowledge docs.** Docs are checked into the repo (not user-supplied at runtime) and the agent's tool surface is narrow — it cannot exfiltrate data or call arbitrary URLs.
- **Unsafe task values.** Duration cap (1–240 min) and category enum reject wild values even if hallucinated.

### AI collaboration

I used Claude Code throughout. **Helpful suggestion**: the `AgentStep` dataclass + JSONL logger design — that gave me the reasoning-trace UI and behavioral eval assertions almost for free. **Flawed suggestion**: an early RAG scoring formula (`overlap / sqrt(|query| × |chunk|)`) caused short chunks to beat long ones on relevance — caught by running test queries before integrating, switched to TF + heading-boost scoring.
