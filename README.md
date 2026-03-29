# PawPal+ (Module 2 Project)

**PawPal+** is a Streamlit app that helps busy pet owners plan and manage daily care tasks for their pets. It considers time constraints and task priorities to generate a smart daily schedule.

## Demo

![PawPal App](pawpal_demo.png)
![PawPal App](pawpal_demo2.png)
![PawPal App](pawpal_demo3.png)
![PawPal App](pawpal_demo4.png)
![PawPal App](pawpal_demo5.png)

## Features

- **Owner & Pet Profiles** - Set up your name, available time, and add multiple pets with breed/species/age details
- **Task Management** - Create care tasks (walks, feeding, meds, grooming, enrichment) with duration, priority, and frequency
- **Priority-Based Scheduling** - Generates a daily plan that prioritizes high-priority tasks first, using shortest duration as a tiebreaker
- **Sort by Duration** - Toggle to sort tasks shortest-first for a quick-win approach
- **Recurring Tasks** - Daily tasks auto-reschedule for tomorrow, weekly tasks for next week, using Python's `timedelta`
- **Conflict Detection** - Warns about duplicate tasks, same-category overlaps on the same day, and when total task time exceeds available time
- **Task Completion** - Mark tasks done directly in the UI, with automatic scheduling of the next occurrence for recurring tasks
- **Plan Reasoning** - Expandable explanation of why tasks were scheduled or skipped

## Testing PawPal+

Run the test suite with:

```bash
python -m pytest
```

The 13 tests cover:

- **Task basics** - marking tasks complete, adding tasks to pets
- **Sorting** - verifying sort by time (shortest first) and sort by priority (high first)
- **Recurring tasks** - daily tasks reschedule for tomorrow, weekly for next week, as-needed tasks don't recur
- **Conflict detection** - catches duplicate task names, same-category overlaps, and time overload warnings
- **Edge cases** - empty task lists produce empty plans, lower-priority tasks get skipped when time runs out

**Confidence Level: 4/5 stars** - The core scheduling logic, recurrence, and conflict detection are well covered. The main gap is that we haven't tested the Streamlit UI integration or more complex multi-pet scenarios, but the backend logic is solid.

## Getting Started

### Setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Run the app

```bash
streamlit run app.py
```

### Project Structure

- `app.py` - Streamlit UI layer
- `pawpal_system.py` - Backend classes (Task, Pet, Owner, Scheduler, DailyPlan)
- `main.py` - Terminal demo script for testing logic
- `tests/test_pawpal.py` - Automated test suite
- `mermaid_final.txt` - Final UML class diagram (Mermaid.js)
