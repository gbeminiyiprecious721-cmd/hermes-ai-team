"""Product Factory: bounded rework loop QA -> Lead Engineer -> QA (run on the server).
When the QA gate fails and QA reported concrete findings, the Lead Engineer gets those findings as a rework request (Claude Code edits the
existing project files), the Lead Engineer gate is re-checked (including the pipeline-run sandbox tests), and QA runs again. Max 2 rounds.
Each round is recorded on the project (state["rework_rounds"] + activity) so Mission Control can show it. Validated before replacing the live file."""
import py_compile
import shutil
import time

p = "/root/.hermes/profiles/product-factory/skills/hermes-director/director.py"
s = open(p, encoding="utf-8").read()
assert "_qa_rework_loop" not in s, "already patched"

# 1) rework feedback reaches the Lead Engineer prompt (wrap the prompt builder)
old_def = "def build_specialist_prompt(specialist: str, context: dict, policy: dict) -> str:"
assert s.count(old_def) == 1
s = s.replace(old_def, "def _build_specialist_prompt_base(specialist: str, context: dict, policy: dict) -> str:", 1)

HELPERS = '''MAX_QA_REWORK_ROUNDS = 2


def build_specialist_prompt(specialist: str, context: dict, policy: dict) -> str:
    """Base prompt, plus a rework request when QA sent findings back to the Lead Engineer."""
    prompt = _build_specialist_prompt_base(specialist, context, policy)
    feedback = context.get("rework_feedback") if isinstance(context, dict) else None
    if specialist == "Lead Engineer" and feedback:
        prompt += (
            "\\n\\nREWORK REQUEST (round " + str(context.get("rework_round", 1)) + " of " + str(MAX_QA_REWORK_ROUNDS) + "). "
            "The independent QA Agent reviewed your implementation and reported the findings below. The project files already exist in the "
            "project folder: read them, then fix the real defects with your Edit/Write tools (keep every file inside the project folder). "
            "Fix what violates the acceptance criteria or is a genuine robustness, correctness or security defect. If you decline a finding, "
            "say why in the evidence list. Update the unit tests to cover the fixes. Return the same JSON object as before, with files_changed "
            "listing every project file. You cannot run the tests; the pipeline runs them and QA will re-check.\\n\\nQA FINDINGS:\\n" + str(feedback)
        )
    return prompt


def _qa_feedback_text(result: dict) -> str:
    """Turn a QA result into a compact rework request (bugs, recommendations, failing test runs, failed edge cases)."""
    artifacts = _extract_artifacts(result) or {}
    parts = []
    for key in ("bugs_found", "recommendations"):
        value = artifacts.get(key)
        if value:
            parts.append(key + ": " + json.dumps(value)[:3500])
    runs = artifacts.get("test_results")
    if isinstance(runs, list):
        failing = [r for r in runs if isinstance(r, dict) and r.get("exit_code") not in (0, None)]
        if failing:
            parts.append("failing_test_runs: " + json.dumps(failing)[:2000])
    edge = artifacts.get("edge_case_results")
    if edge:
        parts.append("edge_case_results: " + json.dumps(edge)[:1500])
    return "\\n".join(parts)[:7500]


def _qa_rework_loop(state: dict, state_file: Path, context: dict, state_dir: Path, policy: dict,
                    quality_gates: list, invoke_fn: Callable, result: dict, aggregate: dict) -> tuple:
    """Bounded QA -> Lead Engineer -> QA loop. Returns the latest (qa_result, qa_aggregate)."""
    state.setdefault("rework_rounds", [])
    for round_no in range(1, MAX_QA_REWORK_ROUNDS + 1):
        feedback = _qa_feedback_text(result)
        if not feedback or result.get("status") != "SUCCESS":
            break                                   # nothing concrete to send back (e.g. QA itself could not run)
        chain = get_execution_chain("Lead Engineer", policy)
        state["current_phase"] = f"REWORK_LEAD_ENGINEER_ROUND_{round_no}"
        state["current_milestone"] = f"Rework round {round_no}/{MAX_QA_REWORK_ROUNDS} - Lead Engineer fixing QA findings"
        state["specialist_in_progress"] = "Lead Engineer"
        state["active_worker"] = chain[0] if chain else None
        state["next_action"] = "Lead Engineer is fixing the defects reported by QA."
        state["updated_at"] = _utc_timestamp()
        record_activity(state, "REWORK_STARTED", f"QA findings sent to the Lead Engineer (round {round_no}).",
                        specialist="Lead Engineer", round=round_no)
        _write_json_file(state_file, state)

        rework_context = dict(context)
        rework_context["rework_feedback"] = feedback
        rework_context["rework_round"] = round_no
        le_result = invoke_fn("Lead Engineer", rework_context, state_dir, policy)
        le_aggregate = validate_specialist_gates("Lead Engineer", le_result, state_dir, quality_gates)
        state["specialist_gate_status"]["Lead Engineer"] = le_aggregate["status"]
        for gate, gate_result in le_aggregate["gates"].items():
            state["gate_status"][gate] = gate_result
        state["worker_used"]["Lead Engineer"] = _extract_worker(le_result)
        entry = {"round": round_no, "qa_findings_chars": len(feedback), "lead_engineer_gate": le_aggregate["status"],
                 "lead_engineer_worker": state["worker_used"]["Lead Engineer"]}
        if le_aggregate["status"] != "PASS":
            entry["stopped"] = "Lead Engineer gate failed: " + str(le_aggregate.get("reason"))[:200]
            state["rework_rounds"].append(entry)
            record_activity(state, "REWORK_STOPPED", entry["stopped"], specialist="Lead Engineer", round=round_no)
            _write_json_file(state_file, state)
            return le_result, le_aggregate          # the blocker is now the Lead Engineer's, report that honestly

        # QA looks again at the reworked project (fresh context so it reads the new Lead Engineer output)
        key = "lead_engineer"
        refreshed = _read_json_file(state_dir / "outputs" / f"{key}.json", {})
        qa_context = dict(context)
        qa_context["outputs"] = dict(context.get("outputs", {}))
        if refreshed:
            qa_context["outputs"]["Lead Engineer"] = refreshed
        state["current_phase"] = f"REWORK_QA_ROUND_{round_no}"
        state["current_milestone"] = f"Rework round {round_no}/{MAX_QA_REWORK_ROUNDS} - QA re-checking"
        state["specialist_in_progress"] = "QA Agent"
        chain_qa = get_execution_chain("QA Agent", policy)
        state["active_worker"] = chain_qa[0] if chain_qa else None
        state["updated_at"] = _utc_timestamp()
        _write_json_file(state_file, state)
        result = invoke_fn("QA Agent", qa_context, state_dir, policy)
        aggregate = validate_specialist_gates("QA Agent", result, state_dir, quality_gates)
        entry["qa_gate_after"] = aggregate["status"]
        state["rework_rounds"].append(entry)
        record_activity(state, "REWORK_COMPLETED", f"Round {round_no}: QA gate {aggregate['status']} after rework.",
                        specialist="QA Agent", round=round_no, qa_gate=aggregate["status"])
        _write_json_file(state_file, state)
        if aggregate["status"] == "PASS":
            break
    return result, aggregate


'''
a = s.index("def run_project(")
prev_line = s[s.rfind("\n", 0, s.rfind("\n", 0, a)) + 1:a].strip()
assert not prev_line.startswith("@"), "decorator above run_project"
s = s[:a] + HELPERS + s[a:]

# 2) hook the loop into run_project right after the QA gate is evaluated
old = '''        result = invoke_fn(specialist, context, state_dir, policy)
        aggregate = validate_specialist_gates(
            specialist, result, state_dir, quality_gates)
        state["specialist_gate_status"][specialist] = aggregate["status"]'''
new = '''        result = invoke_fn(specialist, context, state_dir, policy)
        aggregate = validate_specialist_gates(
            specialist, result, state_dir, quality_gates)
        if specialist == "QA Agent" and aggregate["status"] != "PASS":
            result, aggregate = _qa_rework_loop(
                state, state_file, context, state_dir, policy, quality_gates, invoke_fn, result, aggregate)
        state["specialist_gate_status"][specialist] = aggregate["status"]'''
assert s.count(old) == 1, s.count(old)
s = s.replace(old, new, 1)

shutil.copy(p, "/root/backups/manual-changes/director.py.before-rework-" + time.strftime("%Y%m%d-%H%M%S"))
tmp = p + ".new"
open(tmp, "w", encoding="utf-8").write(s)
py_compile.compile(tmp, doraise=True)
shutil.move(tmp, p)
print("patched: QA -> Lead Engineer -> QA rework loop (max 2 rounds)")
