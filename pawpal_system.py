from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import List, Optional


@dataclass
class Task:
    name: str
    category: str  # walk, feeding, meds, grooming, enrichment
    duration: int  # in minutes
    priority: str  # high, medium, low
    frequency: str = "daily"  # daily, weekly, as-needed
    completed: bool = False
    due_date: Optional[date] = None

    def __post_init__(self):
        """Set due_date to today if not provided."""
        if self.due_date is None:
            self.due_date = date.today()

    def mark_complete(self) -> Optional["Task"]:
        """Mark this task as completed. Returns a new Task for the next occurrence if recurring."""
        self.completed = True
        if self.frequency == "daily":
            return Task(
                name=self.name,
                category=self.category,
                duration=self.duration,
                priority=self.priority,
                frequency=self.frequency,
                due_date=self.due_date + timedelta(days=1),
            )
        elif self.frequency == "weekly":
            return Task(
                name=self.name,
                category=self.category,
                duration=self.duration,
                priority=self.priority,
                frequency=self.frequency,
                due_date=self.due_date + timedelta(weeks=1),
            )
        return None  # "as-needed" tasks don't auto-recur

    def is_due(self, check_date: date = None) -> bool:
        """Check if this task is due on the given date (defaults to today)."""
        if check_date is None:
            check_date = date.today()
        return self.due_date <= check_date

    def get_summary(self) -> str:
        """Return a brief description of the task."""
        status = "Done" if self.completed else "Pending"
        return f"{self.name} [{self.category}] - {self.duration}min, {self.priority} priority, {self.frequency}, due {self.due_date} ({status})"


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

    def mark_task_complete(self, task_name: str) -> Optional[Task]:
        """Mark a task complete and auto-schedule the next occurrence if recurring."""
        for task in self.tasks:
            if task.name == task_name and not task.completed:
                next_task = task.mark_complete()
                if next_task:
                    self.tasks.append(next_task)
                return next_task
        return None

    def get_pending_tasks(self) -> List[Task]:
        """Return all tasks that haven't been completed yet."""
        return [t for t in self.tasks if not t.completed]

    def get_summary(self) -> str:
        """Return a brief description of the pet."""
        return f"{self.name} ({self.species}, {self.breed}, {self.age}yr) - {len(self.tasks)} tasks"


@dataclass
class Employee:
    name: str
    available_minutes: int
    assigned_tasks: List[dict] = field(default_factory=list)

    @property
    def minutes_used(self) -> int:
        return sum(t["duration"] for t in self.assigned_tasks)

    @property
    def minutes_remaining(self) -> int:
        return self.available_minutes - self.minutes_used

    def get_summary(self) -> str:
        return (
            f"{self.name} — {self.available_minutes}min available, "
            f"{self.minutes_used}min assigned, {self.minutes_remaining}min remaining, "
            f"{len(self.assigned_tasks)} tasks"
        )


@dataclass
class Owner:
    name: str
    available_minutes: int
    pets: List[Pet] = field(default_factory=list)
    employees: List[Employee] = field(default_factory=list)

    def add_pet(self, pet: Pet) -> None:
        self.pets.append(pet)

    def add_employee(self, employee: Employee) -> None:
        self.employees.append(employee)

    def get_all_tasks(self) -> List[Task]:
        all_tasks = []
        for pet in self.pets:
            all_tasks.extend(pet.tasks)
        return all_tasks

    def get_all_pending_tasks(self) -> List[Task]:
        pending = []
        for pet in self.pets:
            pending.extend(pet.get_pending_tasks())
        return pending

    def assign_tasks_to_employees(self) -> dict:
        """Greedy assignment: highest-priority tasks first, to the employee
        with the most remaining time who can still fit the task."""
        for emp in self.employees:
            emp.assigned_tasks = []

        pending = []
        for pet in self.pets:
            for task in pet.get_pending_tasks():
                pending.append((pet, task))

        pending.sort(key=lambda x: (PRIORITY_ORDER.get(x[1].priority, 99), x[1].duration))

        unassigned = []
        for pet, task in pending:
            eligible = [e for e in self.employees if e.minutes_remaining >= task.duration]
            if eligible:
                # Pick the least-loaded employee who can still fit the task.
                # This balances work across employees rather than concentrating it.
                best = min(eligible, key=lambda e: e.minutes_used)
                best.assigned_tasks.append({
                    "pet": pet.name,
                    "task": task.name,
                    "category": task.category,
                    "duration": task.duration,
                    "priority": task.priority,
                })
            else:
                unassigned.append({
                    "pet": pet.name,
                    "task": task.name,
                    "duration": task.duration,
                    "priority": task.priority,
                })

        return {
            "assignments": {
                emp.name: {
                    "available_minutes": emp.available_minutes,
                    "minutes_used": emp.minutes_used,
                    "minutes_remaining": emp.minutes_remaining,
                    "tasks": emp.assigned_tasks,
                }
                for emp in self.employees
            },
            "unassigned": unassigned,
        }

    def get_summary(self) -> str:
        pet_names = ", ".join(p.name for p in self.pets) if self.pets else "No pets"
        return (
            f"{self.name} — {self.available_minutes}min available — "
            f"Pets: {pet_names} — Employees: {len(self.employees)}"
        )


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

    def sort_by_time(self, tasks: List[Task] = None) -> List[Task]:
        """Sort tasks by duration (shortest first)."""
        target = tasks if tasks is not None else self.tasks
        return sorted(target, key=lambda t: t.duration)

    def sort_by_priority(self, tasks: List[Task] = None) -> List[Task]:
        """Sort tasks by priority (high first), then duration as tiebreaker."""
        target = tasks if tasks is not None else self.tasks
        return sorted(target, key=lambda t: (PRIORITY_ORDER.get(t.priority, 99), t.duration))

    def filter_by_status(self, completed: bool) -> List[Task]:
        """Filter tasks by completion status."""
        return [t for t in self.tasks if t.completed == completed]

    def filter_by_pet(self, owner: "Owner", pet_name: str) -> List[Task]:
        """Filter tasks belonging to a specific pet."""
        for pet in owner.pets:
            if pet.name == pet_name:
                return list(pet.tasks)
        return []

    def filter_by_category(self, category: str) -> List[Task]:
        """Filter tasks by category."""
        return [t for t in self.tasks if t.category == category]

    def detect_conflicts(self) -> List[str]:
        """Detect scheduling conflicts and return warning messages."""
        warnings = []
        pending = self.filter_by_status(completed=False)

        # Check for duplicate task names on the same due date
        seen = {}
        for task in pending:
            key = (task.name, task.due_date)
            if key in seen:
                warnings.append(
                    f"Conflict: '{task.name}' is scheduled more than once on {task.due_date}."
                )
            else:
                seen[key] = task

        # Check for same-category tasks on the same date that could overlap
        category_by_date = {}
        for task in pending:
            key = (task.category, task.due_date)
            if key in category_by_date:
                other = category_by_date[key]
                warnings.append(
                    f"Warning: '{task.name}' and '{other.name}' are both {task.category} tasks on {task.due_date}. Consider spacing them out."
                )
            else:
                category_by_date[key] = task

        # Check if total pending time exceeds available time
        total_pending = sum(t.duration for t in pending)
        if total_pending > self.available_minutes:
            warnings.append(
                f"Warning: Total pending task time ({total_pending}min) exceeds available time ({self.available_minutes}min). Some tasks will be skipped."
            )

        return warnings

    def generate_plan(self) -> DailyPlan:
        """Generate a daily plan based on task priorities and time constraints."""
        pending = self.filter_by_status(completed=False)
        sorted_tasks = self.sort_by_priority(pending)

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
