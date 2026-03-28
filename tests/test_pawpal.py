from pawpal_system import Task, Pet


def test_mark_complete_changes_status():
    task = Task(name="Morning Walk", category="walk", duration=30, priority="high")
    assert task.completed is False
    task.mark_complete()
    assert task.completed is True


def test_add_task_increases_count():
    pet = Pet(name="Buddy", species="Dog", breed="Golden Retriever", age=4)
    assert len(pet.tasks) == 0
    pet.add_task(Task(name="Walk", category="walk", duration=30, priority="high"))
    assert len(pet.tasks) == 1
    pet.add_task(Task(name="Feed", category="feeding", duration=10, priority="high"))
    assert len(pet.tasks) == 2
