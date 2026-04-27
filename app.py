import os

import streamlit as st
from dotenv import load_dotenv

from pawpal_system import Owner, Pet, Task, Scheduler

load_dotenv()

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

st.title("🐾 PawPal+")

st.markdown(
    "A pet care planning assistant that helps you stay on top of daily tasks. "
    "Talk to the AI agent below or fill out the structured forms further down."
)

st.divider()

# --- Owner Setup ---
st.subheader("Owner Setup")

if st.session_state.owner is None:
    owner_name = st.text_input("Your name", value="")
    available_minutes = st.number_input("Available minutes today", min_value=10, max_value=480, value=60)

    if st.button("Save Owner Profile"):
        if owner_name.strip():
            st.session_state.owner = Owner(name=owner_name.strip(), available_minutes=available_minutes)
            st.rerun()
        else:
            st.warning("Please enter your name.")
else:
    owner = st.session_state.owner
    st.success(f"Owner: {owner.name} | Available time: {owner.available_minutes} minutes")
    if st.button("Reset Profile"):
        st.session_state.owner = None
        st.session_state.chat_history = []
        st.session_state.chat_traces = []
        st.rerun()

st.divider()

# --- AI Agent Chat ---
st.subheader("🤖 Chat with PawPal+ Agent")

if st.session_state.owner is None:
    st.info("Set up your owner profile to start chatting with the agent.")
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

# --- Add a Pet ---
st.subheader("Add a Pet")

if st.session_state.owner is None:
    st.info("Set up your owner profile first.")
else:
    owner = st.session_state.owner

    col1, col2 = st.columns(2)
    with col1:
        pet_name = st.text_input("Pet name", value="")
        species = st.selectbox("Species", ["Dog", "Cat", "Other"])
    with col2:
        breed = st.text_input("Breed", value="")
        age = st.number_input("Age", min_value=0, max_value=30, value=1)

    if st.button("Add Pet"):
        if pet_name.strip():
            new_pet = Pet(name=pet_name.strip(), species=species, breed=breed.strip(), age=age)
            owner.add_pet(new_pet)
            st.rerun()
        else:
            st.warning("Please enter a pet name.")

    # Show current pets
    if owner.pets:
        st.markdown("**Your Pets:**")
        for pet in owner.pets:
            st.write(f"- {pet.get_summary()}")
    else:
        st.info("No pets added yet.")

st.divider()

# --- Add Tasks ---
st.subheader("Add Tasks")

if st.session_state.owner is None or not st.session_state.owner.pets:
    st.info("Add at least one pet before creating tasks.")
else:
    owner = st.session_state.owner
    pet_names = [p.name for p in owner.pets]
    selected_pet_name = st.selectbox("Assign task to pet", pet_names)

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

    # Show all tasks grouped by pet as tables
    for pet in owner.pets:
        if pet.tasks:
            st.markdown(f"**{pet.name}'s Tasks:**")
            task_data = []
            for task in pet.tasks:
                task_data.append({
                    "Task": task.name,
                    "Category": task.category,
                    "Duration": f"{task.duration} min",
                    "Priority": task.priority,
                    "Frequency": task.frequency,
                    "Status": "Done" if task.completed else "Pending",
                })
            st.table(task_data)

            # Mark task complete
            pending = pet.get_pending_tasks()
            if pending:
                task_to_complete = st.selectbox(
                    f"Mark a task complete for {pet.name}",
                    ["-- Select --"] + [t.name for t in pending],
                    key=f"complete_{pet.name}",
                )
                if st.button(f"Complete Task for {pet.name}", key=f"btn_complete_{pet.name}"):
                    if task_to_complete != "-- Select --":
                        next_task = pet.mark_task_complete(task_to_complete)
                        if next_task:
                            st.success(f"'{task_to_complete}' completed! Next occurrence scheduled for {next_task.due_date}.")
                        else:
                            st.success(f"'{task_to_complete}' completed!")
                        st.rerun()

st.divider()

# --- Generate Schedule ---
st.subheader("Generate Daily Schedule")

if st.session_state.owner is None:
    st.info("Set up your profile and add tasks first.")
elif not st.session_state.owner.get_all_tasks():
    st.info("Add some tasks before generating a schedule.")
else:
    owner = st.session_state.owner

    sort_option = st.radio("Sort tasks by:", ["Priority (recommended)", "Duration (shortest first)"], horizontal=True)

    if st.button("Generate Schedule"):
        all_tasks = owner.get_all_tasks()
        scheduler = Scheduler(tasks=all_tasks, available_minutes=owner.available_minutes)

        # Show conflict warnings
        conflicts = scheduler.detect_conflicts()
        if conflicts:
            for warning in conflicts:
                st.warning(warning)

        plan = scheduler.generate_plan()

        # Sort scheduled tasks based on user preference
        if sort_option == "Duration (shortest first)":
            plan.scheduled_tasks = scheduler.sort_by_time(plan.scheduled_tasks)

        # Display scheduled tasks
        st.markdown("### Today's Plan")
        if plan.scheduled_tasks:
            scheduled_data = []
            for i, task in enumerate(plan.scheduled_tasks, 1):
                scheduled_data.append({
                    "#": i,
                    "Task": task.name,
                    "Category": task.category,
                    "Duration": f"{task.duration} min",
                    "Priority": task.priority,
                })
            st.table(scheduled_data)
            st.success(f"Total scheduled time: {plan.total_time_used} / {owner.available_minutes} minutes")
        else:
            st.info("No pending tasks to schedule.")

        # Display skipped tasks
        if plan.skipped_tasks:
            st.markdown("### Skipped Tasks")
            skipped_data = []
            for task in plan.skipped_tasks:
                skipped_data.append({
                    "Task": task.name,
                    "Category": task.category,
                    "Duration": f"{task.duration} min",
                    "Priority": task.priority,
                    "Reason": "Not enough time",
                })
            st.table(skipped_data)

        # Reasoning
        with st.expander("Why this plan?"):
            st.text(plan.get_reasoning())
