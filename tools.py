"""Tool schemas + handlers for the PawPal+ agent.

Each tool is a thin wrapper around an existing `pawpal_system` operation, plus
RAG retrieval. Schemas are intentionally explicit (every field documented) so
Claude's tool calls are predictable and easy to log.
"""

from typing import Any

from pawpal_system import Owner, Pet, Task, Scheduler
from rag import retrieve, format_retrievals
from guardrails import validate_task_input, VALID_CATEGORIES, VALID_PRIORITIES, VALID_FREQUENCIES


# --- Tool schemas (sent to Claude as the `tools` parameter) -----------------

TOOL_SCHEMAS = [
    {
        "name": "list_pets_and_tasks",
        "description": (
            "List every pet the owner has registered and each pet's current tasks. "
            "Always call this first when starting a new conversation so you know "
            "what data exists. Returns a structured summary (no arguments)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "add_pet",
        "description": (
            "Register a new pet under the owner. Use this when the user mentions "
            "a pet that isn't already in the list. Required for any task to be "
            "assigned to that pet."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Pet's name."},
                "species": {
                    "type": "string",
                    "enum": ["Dog", "Cat", "Other"],
                    "description": "Pet's species. Use 'Other' for anything besides dog/cat.",
                },
                "breed": {"type": "string", "description": "Breed (free text)."},
                "age": {"type": "integer", "description": "Age in years."},
            },
            "required": ["name", "species", "breed", "age"],
        },
    },
    {
        "name": "add_task",
        "description": (
            "Add a care task for a specific pet. Choose category, duration, "
            "priority, and frequency thoughtfully — these drive the daily "
            "schedule. Look up care guidelines first if you're unsure about "
            "appropriate durations or cadences for the breed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pet_name": {"type": "string", "description": "Name of the pet to assign to."},
                "name": {"type": "string", "description": "Short task name (e.g. 'Morning Walk')."},
                "category": {
                    "type": "string",
                    "enum": sorted(VALID_CATEGORIES),
                    "description": "Type of care.",
                },
                "duration": {
                    "type": "integer",
                    "description": "Estimated time in minutes (1-240).",
                },
                "priority": {
                    "type": "string",
                    "enum": sorted(VALID_PRIORITIES),
                    "description": "Higher-priority tasks get scheduled first.",
                },
                "frequency": {
                    "type": "string",
                    "enum": sorted(VALID_FREQUENCIES),
                    "description": "How often the task recurs.",
                },
            },
            "required": ["pet_name", "name", "category", "duration", "priority", "frequency"],
        },
    },
    {
        "name": "mark_task_complete",
        "description": (
            "Mark a task complete for a pet. Recurring tasks auto-schedule the "
            "next occurrence (next day for daily, next week for weekly)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pet_name": {"type": "string"},
                "task_name": {"type": "string"},
            },
            "required": ["pet_name", "task_name"],
        },
    },
    {
        "name": "generate_schedule",
        "description": (
            "Generate today's daily plan based on all pending tasks and the "
            "owner's available time. Returns the scheduled tasks (in priority "
            "order), any tasks that didn't fit, and a reasoning summary."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "detect_conflicts",
        "description": (
            "Run conflict detection across all pending tasks. Catches duplicate "
            "task names on the same day, multiple tasks of the same category on "
            "the same day, and total time exceeding the owner's available "
            "minutes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "lookup_care_guideline",
        "description": (
            "Search the curated pet-care knowledge base for guidance on "
            "exercise, feeding, grooming, medication cadence, or warning signs. "
            "Use this BEFORE recommending durations, frequencies, or specific "
            "care practices, especially for breed-specific advice. The knowledge "
            "base covers dogs, cats, common medications, and emergency signs."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What you want to know (e.g. 'exercise needs for a senior dog').",
                },
                "species": {
                    "type": "string",
                    "description": "Optional: 'dog' or 'cat' to bias retrieval.",
                },
                "breed": {
                    "type": "string",
                    "description": "Optional: specific breed for more targeted retrieval.",
                },
            },
            "required": ["query"],
        },
    },
]


# --- Handlers ---------------------------------------------------------------


class ToolError(Exception):
    """Raised by handlers to signal a non-fatal tool error to the agent."""


def _find_pet(owner: Owner, pet_name: str) -> Pet:
    for pet in owner.pets:
        if pet.name.lower() == pet_name.lower():
            return pet
    raise ToolError(
        f"No pet named {pet_name!r} found. Existing pets: "
        f"{[p.name for p in owner.pets] or 'none'}. Use add_pet to register a new one."
    )


def list_pets_and_tasks(owner: Owner) -> dict[str, Any]:
    if not owner.pets:
        return {
            "owner": owner.name,
            "available_minutes": owner.available_minutes,
            "pets": [],
            "note": "No pets registered yet. Use add_pet to register one.",
        }
    return {
        "owner": owner.name,
        "available_minutes": owner.available_minutes,
        "pets": [
            {
                "name": pet.name,
                "species": pet.species,
                "breed": pet.breed,
                "age": pet.age,
                "tasks": [
                    {
                        "name": t.name,
                        "category": t.category,
                        "duration": t.duration,
                        "priority": t.priority,
                        "frequency": t.frequency,
                        "completed": t.completed,
                        "due_date": str(t.due_date),
                    }
                    for t in pet.tasks
                ],
            }
            for pet in owner.pets
        ],
    }


def add_pet(owner: Owner, name: str, species: str, breed: str, age: int) -> dict[str, Any]:
    if not name.strip():
        raise ToolError("Pet name cannot be empty.")
    for existing in owner.pets:
        if existing.name.lower() == name.lower():
            raise ToolError(f"A pet named {name!r} already exists.")
    pet = Pet(name=name.strip(), species=species, breed=breed.strip(), age=age)
    owner.add_pet(pet)
    return {"status": "added", "pet": pet.get_summary()}


def add_task(
    owner: Owner,
    pet_name: str,
    name: str,
    category: str,
    duration: int,
    priority: str,
    frequency: str,
) -> dict[str, Any]:
    pet = _find_pet(owner, pet_name)
    check = validate_task_input(name, category, duration, priority, frequency)
    if not check.allowed:
        raise ToolError(check.reason)

    task = Task(
        name=name.strip(),
        category=category,
        duration=int(duration),
        priority=priority,
        frequency=frequency,
    )
    pet.add_task(task)
    return {
        "status": "added",
        "pet": pet.name,
        "task": task.get_summary(),
    }


def mark_task_complete(owner: Owner, pet_name: str, task_name: str) -> dict[str, Any]:
    pet = _find_pet(owner, pet_name)
    next_task = pet.mark_task_complete(task_name)
    if next_task is None:
        # Either the task wasn't found or it was non-recurring.
        for t in pet.tasks:
            if t.name == task_name and t.completed:
                return {"status": "completed", "pet": pet.name, "task": task_name, "next": None}
        raise ToolError(
            f"No pending task named {task_name!r} for {pet.name}. "
            f"Pending: {[t.name for t in pet.get_pending_tasks()] or 'none'}."
        )
    return {
        "status": "completed",
        "pet": pet.name,
        "task": task_name,
        "next_occurrence": str(next_task.due_date),
    }


def generate_schedule(owner: Owner) -> dict[str, Any]:
    all_tasks = owner.get_all_tasks()
    scheduler = Scheduler(tasks=all_tasks, available_minutes=owner.available_minutes)
    plan = scheduler.generate_plan()
    return {
        "scheduled": [
            {"name": t.name, "category": t.category, "duration": t.duration, "priority": t.priority}
            for t in plan.scheduled_tasks
        ],
        "skipped": [
            {"name": t.name, "category": t.category, "duration": t.duration, "priority": t.priority}
            for t in plan.skipped_tasks
        ],
        "total_minutes": plan.total_time_used,
        "available_minutes": owner.available_minutes,
        "reasoning": plan.get_reasoning(),
    }


def detect_conflicts(owner: Owner) -> dict[str, Any]:
    all_tasks = owner.get_all_tasks()
    scheduler = Scheduler(tasks=all_tasks, available_minutes=owner.available_minutes)
    warnings = scheduler.detect_conflicts()
    return {"conflict_count": len(warnings), "warnings": warnings}


def lookup_care_guideline(query: str, species: str | None = None, breed: str | None = None) -> dict[str, Any]:
    results = retrieve(query, species=species, breed=breed, top_k=2)
    return {
        "query": query,
        "result_count": len(results),
        "results": [
            {
                "source": r.chunk.source,
                "heading": r.chunk.heading,
                "score": round(r.score, 2),
                "excerpt": r.chunk.excerpt(),
            }
            for r in results
        ],
        "formatted": format_retrievals(results),
    }


# --- Dispatcher -------------------------------------------------------------


def dispatch(tool_name: str, tool_input: dict[str, Any], owner: Owner) -> dict[str, Any]:
    """Execute a tool by name. Returns the structured result."""
    handlers = {
        "list_pets_and_tasks": lambda: list_pets_and_tasks(owner),
        "add_pet": lambda: add_pet(owner, **tool_input),
        "add_task": lambda: add_task(owner, **tool_input),
        "mark_task_complete": lambda: mark_task_complete(owner, **tool_input),
        "generate_schedule": lambda: generate_schedule(owner),
        "detect_conflicts": lambda: detect_conflicts(owner),
        "lookup_care_guideline": lambda: lookup_care_guideline(**tool_input),
    }
    if tool_name not in handlers:
        raise ToolError(f"Unknown tool: {tool_name}")
    return handlers[tool_name]()
