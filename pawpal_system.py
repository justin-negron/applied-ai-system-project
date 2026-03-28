from dataclasses import dataclass, field
from typing import List


@dataclass
class Task:
    name: str
    category: str  # walk, feeding, meds, grooming, enrichment
    duration: int  # in minutes
    priority: str  # high, medium, low
    frequency: str = "daily"  # daily, weekly, as-needed
    completed: bool = False

    def mark_complete(self) -> None:
        """Mark this task as completed."""
        self.completed = True

    def reset(self) -> None:
        """Reset task for a new day."""
        self.completed = False

    def get_summary(self) -> str:
        """Return a brief description of the task."""
        status = "Done" if self.completed else "Pending"
        return f"{self.name} [{self.category}] - {self.duration}min, {self.priority} priority, {self.frequency} ({status})"


@dataclass
class Pet:
    name: str
    species: str
    breed: str
    age: int
    tasks: List[Task] = field(default_factory=list)

    def add_task(self, task: Task) -> None:
        """Add a care task for this pet."""
        self.tasks.append(task)

    def remove_task(self, task_name: str) -> bool:
        """Remove a task by name. Returns True if found and removed."""
        for task in self.tasks:
            if task.name == task_name:
                self.tasks.remove(task)
                return True
        return False

    def get_pending_tasks(self) -> List[Task]:
        """Return all tasks that haven't been completed yet."""
        return [t for t in self.tasks if not t.completed]

    def get_summary(self) -> str:
        """Return a brief description of the pet."""
        return f"{self.name} ({self.species}, {self.breed}, {self.age}yr) - {len(self.tasks)} tasks"


@dataclass
class Owner:
    name: str
    available_minutes: int
    pets: List[Pet] = field(default_factory=list)

    def add_pet(self, pet: Pet) -> None:
        """Add a pet to this owner's list."""
        self.pets.append(pet)

    def get_all_tasks(self) -> List[Task]:
        """Get all tasks across all pets."""
        all_tasks = []
        for pet in self.pets:
            all_tasks.extend(pet.tasks)
        return all_tasks

    def get_all_pending_tasks(self) -> List[Task]:
        """Get all pending tasks across all pets."""
        pending = []
        for pet in self.pets:
            pending.extend(pet.get_pending_tasks())
        return pending

    def get_summary(self) -> str:
        """Return a brief description of the owner."""
        pet_names = ", ".join(p.name for p in self.pets) if self.pets else "No pets"
        return f"{self.name} - {self.available_minutes}min available - Pets: {pet_names}"


@dataclass
class DailyPlan:
    scheduled_tasks: List[Task] = field(default_factory=list)
    skipped_tasks: List[Task] = field(default_factory=list)
    total_time_used: int = 0

    def display(self) -> str:
        """Return a formatted view of the daily plan."""
        lines = ["=== Daily Plan ==="]
        lines.append(f"Total time: {self.total_time_used} minutes\n")

        lines.append("Scheduled:")
        if self.scheduled_tasks:
            for i, task in enumerate(self.scheduled_tasks, 1):
                lines.append(f"  {i}. {task.get_summary()}")
        else:
            lines.append("  (none)")

        lines.append("\nSkipped (not enough time):")
        if self.skipped_tasks:
            for task in self.skipped_tasks:
                lines.append(f"  - {task.get_summary()}")
        else:
            lines.append("  (none)")

        return "\n".join(lines)

    def get_reasoning(self) -> str:
        """Explain why tasks were scheduled or skipped."""
        lines = ["=== Scheduling Reasoning ==="]
        lines.append("Tasks were sorted by priority (high > medium > low).")
        lines.append("Higher priority tasks were scheduled first to ensure the most important care gets done.")

        if self.skipped_tasks:
            skipped_names = ", ".join(t.name for t in self.skipped_tasks)
            lines.append(f"\nSkipped tasks ({skipped_names}) didn't fit within the available time.")
            lines.append("Consider increasing available time or reducing task durations.")

        return "\n".join(lines)


PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


class Scheduler:
    def __init__(self, tasks: List[Task], available_minutes: int):
        self.tasks = tasks
        self.available_minutes = available_minutes

    def generate_plan(self) -> DailyPlan:
        """Generate a daily plan based on task priorities and time constraints."""
        # Filter to only pending tasks
        pending = [t for t in self.tasks if not t.completed]

        # Sort by priority (high first), then by duration (shorter first as tiebreaker)
        sorted_tasks = sorted(
            pending,
            key=lambda t: (PRIORITY_ORDER.get(t.priority, 99), t.duration)
        )

        plan = DailyPlan()
        remaining_time = self.available_minutes

        for task in sorted_tasks:
            if task.duration <= remaining_time:
                plan.scheduled_tasks.append(task)
                plan.total_time_used += task.duration
                remaining_time -= task.duration
            else:
                plan.skipped_tasks.append(task)

        return plan
