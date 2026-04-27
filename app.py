import os

import streamlit as st
from dotenv import load_dotenv

from pawpal_system import Owner, Pet, Task, Scheduler, Employee

load_dotenv()


def _seed_pet_hotel_demo(owner: Owner) -> None:
    """Populate a realistic pet-hotel scenario: 3 staff + 8 dogs with breed-accurate tasks."""

    # --- Employees ---
    existing_emp_names = {e.name.lower() for e in owner.employees}
    staff = [
        ("Jacob", 240),   # 4-hour shift
        ("Sierra", 360),  # 6-hour shift
        ("Noah", 360),    # 6-hour shift
    ]
    for name, mins in staff:
        if name.lower() not in existing_emp_names:
            owner.add_employee(Employee(name=name, available_minutes=mins))

    # --- Dogs + tasks ---
    # Schema: (name, species, breed, age, [(task_name, category, duration, priority, frequency)])
    existing_pet_names = {p.name.lower() for p in owner.pets}
    dogs = [
        (
            "Bella", "Dog", "Golden Retriever", 3,
            [
                ("Morning Walk",    "walk",        30, "high",   "daily"),
                ("Morning Feeding", "feeding",     10, "high",   "daily"),
                ("Afternoon Play",  "enrichment",  20, "medium", "daily"),
                ("Evening Walk",    "walk",        25, "medium", "daily"),
                ("Evening Feeding", "feeding",     10, "high",   "daily"),
                ("Coat Brushing",   "grooming",    15, "low",    "daily"),
            ],
        ),
        (
            "Max", "Dog", "German Shepherd", 5,
            [
                ("Morning Walk",      "walk",       30, "high",   "daily"),
                ("Morning Feeding",   "feeding",    10, "high",   "daily"),
                ("Training Session",  "enrichment", 20, "high",   "daily"),
                ("Midday Potty",      "walk",       10, "medium", "daily"),
                ("Evening Feeding",   "feeding",    10, "high",   "daily"),
            ],
        ),
        (
            "Coco", "Dog", "French Bulldog", 2,
            [
                ("Short Morning Walk", "walk",       15, "high",   "daily"),
                ("Morning Feeding",    "feeding",    10, "high",   "daily"),
                ("Indoor Play",        "enrichment", 15, "medium", "daily"),
                ("Evening Feeding",    "feeding",    10, "high",   "daily"),
            ],
        ),
        (
            "Rocky", "Dog", "Labrador Retriever", 1,
            [
                ("Morning Walk",       "walk",       30, "high", "daily"),
                ("Morning Feeding",    "feeding",    10, "high", "daily"),
                ("Puppy Play Session", "enrichment", 30, "high", "daily"),
                ("Midday Potty",       "walk",       10, "high", "daily"),
                ("Evening Feeding",    "feeding",    10, "high", "daily"),
            ],
        ),
        (
            "Luna", "Dog", "Border Collie", 4,
            [
                ("Morning Run",          "walk",       45, "high", "daily"),
                ("Morning Feeding",      "feeding",    10, "high", "daily"),
                ("Mental Enrichment",    "enrichment", 30, "high", "daily"),
                ("Evening Feeding",      "feeding",    10, "high", "daily"),
            ],
        ),
        (
            "Daisy", "Dog", "Chihuahua", 8,
            [
                ("Short Morning Walk", "walk",       10, "high", "daily"),
                ("Morning Feeding",    "feeding",    10, "high", "daily"),
                ("Afternoon Lap Time", "enrichment", 15, "low",  "daily"),
                ("Evening Feeding",    "feeding",    10, "high", "daily"),
            ],
        ),
        (
            "Zeus", "Dog", "Rottweiler", 6,
            [
                ("Morning Walk",            "walk",       30, "high",   "daily"),
                ("Morning Feeding",         "feeding",    10, "high",   "daily"),
                ("Controlled Socialization","enrichment", 20, "medium", "daily"),
                ("Evening Feeding",         "feeding",    10, "high",   "daily"),
            ],
        ),
        (
            "Mia", "Dog", "Miniature Poodle", 4,
            [
                ("Morning Walk",    "walk",      20, "high",   "daily"),
                ("Morning Feeding", "feeding",   10, "high",   "daily"),
                ("Coat Brushing",   "grooming",  20, "high",   "daily"),
                ("Evening Feeding", "feeding",   10, "high",   "daily"),
                ("Evening Walk",    "walk",      15, "medium", "daily"),
            ],
        ),
    ]

    for name, species, breed, age, tasks in dogs:
        if name.lower() in existing_pet_names:
            continue
        pet = Pet(name=name, species=species, breed=breed, age=age)
        for task_name, cat, dur, pri, freq in tasks:
            pet.add_task(Task(name=task_name, category=cat, duration=dur, priority=pri, frequency=freq))
        owner.add_pet(pet)


st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="centered")

# Initialize session state - only runs once per session
if "owner" not in st.session_state:
    st.session_state.owner = None
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "chat_traces" not in st.session_state:
    # Reasoning traces, one per assistant turn — kept separate from the message
    # history that goes back to the model so we don't pollute the prompt.
    st.session_state.chat_traces = []

st.title("🐾 PawPal AI Pro")

st.markdown(
    "A pet care planning assistant that helps you stay on top of daily tasks. "
    "Talk to the AI agent below or fill out the structured forms further down."
)

st.divider()

# --- Admin Setup ---
st.subheader("Admin Setup")

if st.session_state.owner is None:
    admin_name = st.text_input("Your name", value="")

    if st.button("Save Profile"):
        if admin_name.strip():
            st.session_state.owner = Owner(name=admin_name.strip(), available_minutes=480)
            st.rerun()
        else:
            st.warning("Please enter your name.")
else:
    owner = st.session_state.owner
    st.success(f"Logged in as: {owner.name}")
    col_reset, col_demo = st.columns([1, 2])
    with col_reset:
        if st.button("Reset Profile"):
            st.session_state.owner = None
            st.session_state.chat_history = []
            st.session_state.chat_traces = []
            st.rerun()
    with col_demo:
        if st.button("🐾 Load Pet Hotel Demo", help="Pre-populate employees, dogs, and tasks for a realistic pet lodge scenario"):
            _seed_pet_hotel_demo(st.session_state.owner)
            st.rerun()

st.divider()

# --- AI Agent Chat ---
st.subheader("🤖 Chat with PawPal AI Pro Agent")

if st.session_state.owner is None:
    st.info("Complete Admin Setup above to start chatting with the agent.")
elif not os.getenv("ANTHROPIC_API_KEY"):
    st.warning(
        "**ANTHROPIC_API_KEY is not set.** The chat agent needs an Anthropic API key. "
        "Add `ANTHROPIC_API_KEY=...` to a `.env` file in the project root, then restart the app. "
        "You can still use the forms below."
    )
else:
    st.caption(
        "Try: _\"I just got a 3-year-old Lab named Cooper. Set up his morning walk routine.\"_  \n"
        "Or: _\"How long should I walk a French Bulldog in the summer?\"_"
    )

    # Render existing conversation
    for i, msg in enumerate(st.session_state.chat_history):
        with st.chat_message(msg["role"]):
            content = msg["content"] if isinstance(msg["content"], str) else "(tool messages)"
            st.markdown(content)
            # Show the reasoning trace under the assistant turn that produced it.
            if msg["role"] == "assistant":
                trace_idx = sum(
                    1 for m in st.session_state.chat_history[: i + 1] if m["role"] == "assistant"
                ) - 1
                if 0 <= trace_idx < len(st.session_state.chat_traces):
                    trace = st.session_state.chat_traces[trace_idx]
                    with st.expander(
                        f"🔎 Reasoning trace ({len(trace['steps'])} steps, "
                        f"{len(trace['tools_called'])} tool calls"
                        + (f", confidence {trace['confidence']:.2f}" if trace["confidence"] else "")
                        + ")"
                    ):
                        for step in trace["steps"]:
                            kind = step["kind"]
                            if kind == "thinking":
                                st.markdown(f"💭 **Thinking:** {step['payload']['text'][:400]}...")
                            elif kind == "tool_call":
                                st.markdown(
                                    f"🔧 **Tool call:** `{step['payload']['name']}`  \n"
                                    f"```json\n{step['payload']['input']}\n```"
                                )
                            elif kind == "tool_result":
                                marker = "❌" if step["payload"].get("is_error") else "✅"
                                output = step["payload"].get("output", "")
                                st.markdown(
                                    f"{marker} **Tool result:** `{step['payload']['name']}`"
                                )
                                st.code(output[:800], language="json")
                            elif kind == "text":
                                pass  # Already shown in the chat bubble above.
                            elif kind == "error":
                                st.error(f"⚠️ {step['payload']}")

    # Chat input
    user_input = st.chat_input("Ask the agent...")
    if user_input:
        # Render user turn immediately
        with st.chat_message("user"):
            st.markdown(user_input)

        # Run agent — import inside the branch so import errors don't crash the page
        try:
            from agent import run_agent

            with st.spinner("Agent thinking..."):
                # Build a flat history for the model — only role+content text.
                # We do NOT pass the full assistant content (which may include
                # tool_use blocks from the rendered trace) because each user
                # message starts a fresh tool loop.
                history_for_model = [
                    {"role": m["role"], "content": m["content"]}
                    for m in st.session_state.chat_history
                    if isinstance(m["content"], str)
                ]
                result = run_agent(
                    user_input,
                    st.session_state.owner,
                    conversation_history=history_for_model,
                )

            with st.chat_message("assistant"):
                st.markdown(result.text)

            # Persist UI history
            st.session_state.chat_history.append({"role": "user", "content": user_input})
            st.session_state.chat_history.append({"role": "assistant", "content": result.text})
            st.session_state.chat_traces.append(
                {
                    "steps": [{"kind": s.kind, "payload": s.payload} for s in result.steps],
                    "tools_called": result.tools_called,
                    "confidence": result.confidence,
                    "turns_used": result.turns_used,
                }
            )
            st.rerun()
        except Exception as e:
            st.error(f"Agent error: {type(e).__name__}: {e}")

    if st.button("Clear chat", key="clear_chat"):
        st.session_state.chat_history = []
        st.session_state.chat_traces = []
        st.rerun()

st.divider()

# --- Employee Management ---
st.subheader("👥 Employees")

if st.session_state.owner is None:
    st.info("Complete Admin Setup first.")
else:
    owner = st.session_state.owner

    col1, col2 = st.columns(2)
    with col1:
        emp_name = st.text_input("Employee name", key="emp_name")
    with col2:
        emp_hours = st.number_input("Hours available today", min_value=1, max_value=12, value=6, key="emp_hours")

    if st.button("Add Employee"):
        if emp_name.strip():
            for existing in owner.employees:
                if existing.name.lower() == emp_name.strip().lower():
                    st.warning(f"{emp_name.strip()} is already on the team.")
                    break
            else:
                owner.add_employee(Employee(name=emp_name.strip(), available_minutes=emp_hours * 60))
                st.rerun()
        else:
            st.warning("Please enter an employee name.")

    if owner.employees:
        st.markdown("**Current Team:**")
        emp_data = []
        for emp in owner.employees:
            tasks_summary = (
                ", ".join(f"{t['task']} ({t['pet']})" for t in emp.assigned_tasks)
                if emp.assigned_tasks else "—"
            )
            emp_data.append({
                "Name": emp.name,
                "Available": f"{emp.available_minutes // 60}h {emp.available_minutes % 60}m",
                "Assigned": f"{emp.minutes_used} min",
                "Remaining": f"{emp.minutes_remaining} min",
                "Tasks": tasks_summary,
            })
        st.table(emp_data)
    else:
        st.info("No employees added yet.")

st.divider()

# --- Dogs ---
st.subheader("🐕 Dogs")

if st.session_state.owner is None:
    st.info("Complete Admin Setup first.")
else:
    owner = st.session_state.owner

    col1, col2 = st.columns(2)
    with col1:
        pet_name = st.text_input("Dog name", value="")
        species = st.selectbox("Species", ["Dog", "Cat", "Other"])
    with col2:
        breed = st.text_input("Breed", value="")
        age = st.number_input("Age (years)", min_value=0, max_value=30, value=1)

    if st.button("Add Dog"):
        if pet_name.strip():
            new_pet = Pet(name=pet_name.strip(), species=species, breed=breed.strip(), age=age)
            owner.add_pet(new_pet)
            st.rerun()
        else:
            st.warning("Please enter a name.")

    if owner.pets:
        st.markdown("**Dogs in the system:**")
        for pet in owner.pets:
            st.write(f"- {pet.get_summary()}")
    else:
        st.info("No dogs added yet.")

st.divider()

# --- Tasks ---
st.subheader("📝 Tasks")

if st.session_state.owner is None or not st.session_state.owner.pets:
    st.info("Add at least one dog before creating tasks.")
else:
    owner = st.session_state.owner
    pet_names = [p.name for p in owner.pets]
    selected_pet_name = st.selectbox("Assign task to", pet_names)

    col1, col2, col3 = st.columns(3)
    with col1:
        task_name = st.text_input("Task name", value="")
    with col2:
        category = st.selectbox("Category", ["walk", "feeding", "meds", "grooming", "enrichment"])
    with col3:
        duration = st.number_input("Duration (min)", min_value=1, max_value=240, value=15)

    col_a, col_b = st.columns(2)
    with col_a:
        priority = st.selectbox("Priority", ["high", "medium", "low"])
    with col_b:
        frequency = st.selectbox("Frequency", ["daily", "weekly", "as-needed"])

    if st.button("Add Task"):
        if task_name.strip():
            new_task = Task(
                name=task_name.strip(),
                category=category,
                duration=int(duration),
                priority=priority,
                frequency=frequency,
            )
            for pet in owner.pets:
                if pet.name == selected_pet_name:
                    pet.add_task(new_task)
                    break
            st.rerun()
        else:
            st.warning("Please enter a task name.")

    for pet in owner.pets:
        # Only show tasks due today or earlier — future recurrences are hidden
        # until their due date so completing a daily task doesn't look like it
        # immediately comes back.
        todays_tasks = [t for t in pet.tasks if t.is_due()]
        if todays_tasks:
            st.markdown(f"**{pet.name}'s Tasks (today):**")
            task_data = []
            for task in todays_tasks:
                task_data.append({
                    "Task": task.name,
                    "Category": task.category,
                    "Duration": f"{task.duration} min",
                    "Priority": task.priority,
                    "Frequency": task.frequency,
                    "Status": "✅ Done" if task.completed else "Pending",
                })
            st.table(task_data)

            pending_today = [t for t in todays_tasks if not t.completed]
            if pending_today:
                task_to_complete = st.selectbox(
                    f"Mark complete for {pet.name}",
                    ["-- Select --"] + [t.name for t in pending_today],
                    key=f"complete_{pet.name}",
                )
                if st.button(f"Complete Task for {pet.name}", key=f"btn_complete_{pet.name}"):
                    if task_to_complete != "-- Select --":
                        next_task = pet.mark_task_complete(task_to_complete)
                        if next_task:
                            st.success(f"'{task_to_complete}' done! Next occurrence: {next_task.due_date}.")
                        else:
                            st.success(f"'{task_to_complete}' completed!")
                        st.rerun()

st.divider()

# --- Generate Schedule ---
st.subheader("📋 Generate Today's Schedule")

if st.session_state.owner is None:
    st.info("Set up your profile, add pets and tasks first.")
elif not st.session_state.owner.get_all_tasks():
    st.info("Add some tasks before generating a schedule.")
elif not st.session_state.owner.employees:
    st.info("Add at least one employee before generating a schedule.")
else:
    owner = st.session_state.owner
    tab_quick, tab_ai = st.tabs(["⚡ Quick Schedule", "✨ AI Schedule"])

    # --- Quick (deterministic) ---
    with tab_quick:
        st.caption("Priority-based assignment using available employee time. Instant, no API call.")
        if st.button("Generate Quick Schedule"):
            result = owner.assign_tasks_to_employees()

            if any(info["tasks"] for info in result["assignments"].values()):
                for emp_name, info in result["assignments"].items():
                    if info["tasks"]:
                        st.markdown(
                            f"**{emp_name}** — {info['minutes_used']} / {info['available_minutes']} min used"
                        )
                        st.table([
                            {
                                "Pet": t["pet"],
                                "Task": t["task"],
                                "Category": t["category"],
                                "Duration": f"{t['duration']} min",
                                "Priority": t["priority"],
                            }
                            for t in info["tasks"]
                        ])
                    else:
                        st.markdown(f"**{emp_name}** — no tasks assigned")
            else:
                st.info("No pending tasks to assign.")

            if result["unassigned"]:
                st.markdown("### ⚠️ Could Not Assign")
                st.table([
                    {
                        "Task": t["task"],
                        "Pet": t["pet"],
                        "Duration": f"{t['duration']} min",
                        "Priority": t["priority"],
                    }
                    for t in result["unassigned"]
                ])

    # --- AI-powered ---
    with tab_ai:
        st.caption(
            "The AI reviews all dogs, tasks, priorities, and staff schedules to build "
            "the optimal plan and explain its reasoning."
        )
        if st.button("✨ Generate AI Schedule", type="primary"):
            try:
                from agent import run_agent

                emp_summary = ", ".join(
                    f"{e.name} ({e.available_minutes // 60}h {e.available_minutes % 60}m)"
                    for e in owner.employees
                )
                schedule_prompt = (
                    f"Generate today's full schedule. "
                    f"Team working today: {emp_summary}. "
                    f"Review all pet tasks and their priorities, then assign them to employees "
                    f"for maximum coverage — highest priority tasks first, balanced across the team. "
                    f"Summarize each employee's workload and flag anything that couldn't be assigned."
                )

                with st.spinner("AI is building the schedule..."):
                    result = run_agent(schedule_prompt, owner)

                st.markdown("### AI Summary")
                st.markdown(result.text)

                if any(emp.assigned_tasks for emp in owner.employees):
                    st.markdown("### Employee Assignments")
                    for emp in owner.employees:
                        if emp.assigned_tasks:
                            st.markdown(
                                f"**{emp.name}** — {emp.minutes_used} / {emp.available_minutes} min used"
                            )
                            st.table([
                                {
                                    "Pet": t["pet"],
                                    "Task": t["task"],
                                    "Category": t["category"],
                                    "Duration": f"{t['duration']} min",
                                    "Priority": t["priority"],
                                }
                                for t in emp.assigned_tasks
                            ])
                        else:
                            st.markdown(f"**{emp.name}** — no tasks assigned")

                assigned_keys = {
                    (t["pet"], t["task"])
                    for emp in owner.employees
                    for t in emp.assigned_tasks
                }
                unassigned = [
                    t for pet in owner.pets for t in pet.get_pending_tasks()
                    if (pet.name, t.name) not in assigned_keys
                ]
                if unassigned:
                    st.markdown("### ⚠️ Could Not Assign")
                    st.table([
                        {
                            "Pet": next(p.name for p in owner.pets if t in p.tasks),
                            "Task": t.name,
                            "Duration": f"{t.duration} min",
                            "Priority": t.priority,
                        }
                        for t in unassigned
                    ])

                if result.steps:
                    with st.expander(
                        f"🔎 Agent reasoning ({len(result.tools_called)} tool calls"
                        + (f", confidence {result.confidence:.2f}" if result.confidence else "")
                        + ")"
                    ):
                        for step in result.steps:
                            if step.kind == "tool_call":
                                st.markdown(f"🔧 **`{step.payload['name']}`**")
                                st.code(str(step.payload.get("input", "")), language="json")
                            elif step.kind == "tool_result":
                                marker = "❌" if step.payload.get("is_error") else "✅"
                                st.markdown(f"{marker} **Result:** `{step.payload['name']}`")
                                st.code(step.payload.get("output", "")[:600], language="json")
                            elif step.kind == "error":
                                st.error(str(step.payload))

            except Exception as e:
                st.error(f"Schedule generation failed: {type(e).__name__}: {e}")
