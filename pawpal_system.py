from dataclasses import dataclass, field
from typing import List


@dataclass
class Pet:
    name: str
    species: str
    breed: str
    age: int

    def get_summary(self) -> str:
        """Return a brief description of the pet."""
        pass


@dataclass
class Owner:
    name: str
    available_minutes: int
    pet: Pet

    def get_summary(self) -> str:
        """Return a brief description of the owner and their pet."""
        pass


@dataclass
class Task:
    name: str
    category: str  # walk, feeding, meds, grooming, enrichment
    duration: int  # in minutes
    priority: str  # high, medium, low
    completed: bool = False

    def mark_complete(self) -> None:
        """Mark this task as completed."""
        pass

    def get_summary(self) -> str:
        """Return a brief description of the task."""
        pass


@dataclass
class DailyPlan:
    scheduled_tasks: List[Task] = field(default_factory=list)
    skipped_tasks: List[Task] = field(default_factory=list)
    total_time_used: int = 0

    def display(self) -> str:
        """Return a formatted view of the daily plan."""
        pass

    def get_reasoning(self) -> str:
        """Explain why tasks were scheduled or skipped."""
        pass


class Scheduler:
    def __init__(self, tasks: List[Task], available_minutes: int):
        self.tasks = tasks
        self.available_minutes = available_minutes

    def generate_plan(self) -> DailyPlan:
        """Generate a daily plan based on task priorities and time constraints."""
        pass
