from pawpal_system import Owner, Pet, Task, Scheduler

# Create pets
buddy = Pet(name="Buddy", species="Dog", breed="Golden Retriever", age=4)
whiskers = Pet(name="Whiskers", species="Cat", breed="Siamese", age=2)

# Create owner with 60 minutes available
owner = Owner(name="Justin", available_minutes=60)
owner.add_pet(buddy)
owner.add_pet(whiskers)

# Add tasks for Buddy
buddy.add_task(Task(name="Morning Walk", category="walk", duration=30, priority="high"))
buddy.add_task(Task(name="Brush Coat", category="grooming", duration=15, priority="low"))
buddy.add_task(Task(name="Give Heartworm Meds", category="meds", duration=5, priority="high", frequency="weekly"))

# Add tasks for Whiskers
whiskers.add_task(Task(name="Play Session", category="enrichment", duration=20, priority="medium"))
whiskers.add_task(Task(name="Clean Litter Box", category="grooming", duration=10, priority="high"))

# Print owner and pet summaries
print(owner.get_summary())
for pet in owner.pets:
    print(f"  {pet.get_summary()}")
print()

# Generate and display the daily plan
all_tasks = owner.get_all_tasks()
scheduler = Scheduler(tasks=all_tasks, available_minutes=owner.available_minutes)
plan = scheduler.generate_plan()

print(plan.display())
print()
print(plan.get_reasoning())
