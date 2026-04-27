# PawPal+ Applied AI Architecture

## System diagram

```mermaid
flowchart TD
    User([Pet Owner])

    subgraph UI["Interface layer"]
        Streamlit[app.py — Streamlit UI<br/>chat + structured forms]
        CLI[agent.py — CLI demo]
    end

    subgraph AI["AI orchestration layer"]
        Guardrails[guardrails.py<br/>diagnosis & dosage refusal,<br/>task input validation]
        Agent[agent.py — Claude tool-calling loop<br/>claude-opus-4-7, adaptive thinking,<br/>prompt caching]
        Logger[agent_logger.py<br/>logs/agent.jsonl]
    end

    subgraph Tools["Tool surface (tools.py)"]
        Tlist[list_pets_and_tasks]
        Tadd[add_pet / add_task]
        Tcomplete[mark_task_complete]
        Tplan[generate_schedule]
        Tconflict[detect_conflicts]
        Trag[lookup_care_guideline]
    end

    subgraph Backend["Deterministic backend (pawpal_system.py)"]
        Owner[Owner / Pet / Task]
        Scheduler[Scheduler<br/>priority sort, conflict detection,<br/>greedy time-budget plan]
    end

    subgraph RAG["Knowledge layer"]
        Retriever[rag.py<br/>section-chunking + TF scoring<br/>+ species/breed boost]
        Docs[knowledge/*.md<br/>5 curated guidelines:<br/>dog exercise, cat care,<br/>medication schedules,<br/>grooming, warning signs]
    end

    subgraph Eval["Reliability"]
        Tests[tests/<br/>43 unit tests]
        EvalH[eval_agent.py<br/>8 end-to-end scenarios]
    end

    User -->|natural language| Streamlit
    User -->|natural language| CLI
    Streamlit --> Guardrails
    CLI --> Guardrails
    Guardrails -->|allowed| Agent
    Guardrails -.->|refused: vet diagnosis,<br/>medication dosage| Streamlit
    Agent <-->|JSON tool calls| Tools
    Agent --> Logger
    Tools --> Backend
    Trag --> Retriever
    Retriever --> Docs
    Tests -.->|verifies| Tools
    Tests -.->|verifies| Retriever
    Tests -.->|verifies| Guardrails
    EvalH -.->|verifies| Agent

    classDef ai fill:#e8f0fe,stroke:#1967d2
    classDef rag fill:#fef7e0,stroke:#f29900
    classDef eval fill:#fce8e6,stroke:#c5221f
    classDef backend fill:#e6f4ea,stroke:#137333
    class Agent,Guardrails,Logger ai
    class Retriever,Docs rag
    class Tests,EvalH eval
    class Owner,Scheduler,Backend backend
```

## Data flow (typical chat turn)

1. User sends message via Streamlit chat or CLI.
2. `guardrails.check_user_input` scans for diagnosis/dosage requests; if matched, returns a refusal *without* calling the API.
3. Agent loop sends `(system prompt + tool defs + conversation history + user message)` to Claude Opus 4.7 with adaptive thinking. System prompt and tool definitions are cached (`cache_control: ephemeral`) so follow-up turns pay only ~10% of input cost.
4. Claude responds with either text (end of turn) or one or more `tool_use` blocks.
5. For each tool call: `tools.dispatch` runs the corresponding handler against the live `Owner` object or the RAG retriever. Tool input is validated against the same guardrails the structured forms use.
6. Tool results are appended to the message history; the loop continues until Claude emits no more tool calls (capped at 8 iterations as a safety net).
7. Every step (thinking, tool call, tool result, final text, confidence score) is appended to `logs/agent.jsonl` and exposed in the Streamlit "Reasoning trace" expander.

## Why these choices

- **Manual agentic loop** (vs. SDK tool runner): we need per-step observability for the reasoning-trace UI and the eval harness. The runner abstracts that away.
- **Manual RAG** (vs. embeddings + vector DB): the knowledge base is small (5 docs, ~20 chunks) and queries map well to keyword + heading matches. A 50-line scorer is easier to test, explain, and ship than a vector store.
- **Tools wrap existing methods rather than replacing them**: the deterministic scheduler stays the source of truth for what gets scheduled. The agent only orchestrates — it cannot bypass the time budget, the priority sort, or the conflict detector.
- **Two-layer testing**: 43 unit tests cover deterministic pieces (RAG retrieval, tool wrappers, guardrail patterns); the live eval harness (`eval_agent.py`) covers agent behavior. Splitting them keeps the unit suite fast and offline while still measuring end-to-end reliability.
