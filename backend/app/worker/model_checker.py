"""TLA+ compiler and TLC runner for BehavioralModel DSL."""

import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

TLA_TOOLS_JAR = Path(os.getenv("TLA_TOOLS_JAR", "/opt/tla/tla2tools.jar"))
CHECK_TIMEOUT_SECONDS = int(os.getenv("CHECK_TIMEOUT_SECONDS", "120"))
STATE_LIMIT = int(os.getenv("STATE_LIMIT", "1000000"))


class TLCError(Exception):
    """TLC execution error."""

    def __init__(self, message: str, returncode: int | None = None, stderr: str = ""):
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr


def compile_to_tla(model: dict[str, Any]) -> tuple[str, str]:
    """Compile BehavioralModel DSL to TLA+ spec and config."""
    variables = model["variables"]
    initial = model["initial"]
    transitions = model["transitions"]
    properties = model.get("properties", [])

    var_names = [v["name"] for v in variables]
    vars_line = ", ".join(var_names)

    init_lines = []
    for var in variables:
        name = var["name"]
        val = initial[name]
        if var["type"] == "boolean":
            init_lines.append(rf"  /\ {name} = {str(val).upper()}")
        elif var["type"] == "integer":
            init_lines.append(rf"  /\ {name} = {val}")
        else:
            init_lines.append(rf'  /\ {name} = "{val}"')

    trans_lines = []
    for t in transitions:
        name = t["name"]
        guard = _compile_expr(t["guard"])
        effects = []
        for eff in t["effects"]:
            if eff.get("set"):
                var_name, value = eff["set"]
                if isinstance(value, bool):
                    effects.append(rf"  /\ {var_name}' = {str(value).upper()}")
                elif isinstance(value, int):
                    effects.append(rf"  /\ {var_name}' = {value}")
                else:
                    effects.append(f'  /\\ {var_name}\' = "{value}"')
            elif eff.get("inc"):
                var_name, delta = eff["inc"]
                effects.append(rf"  /\ {var_name}' = {var_name} + {delta}")
            elif eff.get("dec"):
                var_name, delta = eff["dec"]
                effects.append(rf"  /\ {var_name}' = {var_name} - {delta}")
        trans_lines.append(f"{name} ==\n{guard}\n" + "\n".join(effects))

    next_line = "  \\/ " + "\n  \\/ ".join(t["name"] for t in transitions)

    tla = rf"""---------------------------- MODULE Model ----------------------------
EXTENDS Naturals, Sequences, TLC

VARIABLES {vars_line}

Init ==
{chr(10).join(init_lines)}

{chr(10).join(trans_lines)}

Next ==
{next_line}

Spec == Init /\ [][Next]_<<{vars_line}>>

======================================================================="""

    prop_lines = []
    for prop in properties:
        if prop["type"] == "invariant":
            expr = _compile_expr(prop["expression"])
            prop_lines.append(f"INVARIANT {prop['id']} == {expr}")
        elif prop["type"] == "forbidden_state":
            expr = _compile_expr(prop["expression"])
            prop_lines.append(f"INVARIANT {prop['id']} == ~({expr})")

    cfg = f"""SPECIFICATION Spec
CONSTANTS
{chr(10).join(prop_lines) if prop_lines else ""}
"""

    return tla, cfg


def _compile_expr(expr: dict[str, Any]) -> str:
    """Compile DSL expression to TLA+ expression."""
    if "eq" in expr:
        left, right = expr["eq"]
        if isinstance(left, dict) and left.get("var"):
            left = left["var"]
        if isinstance(right, bool):
            right = str(right).upper()
        elif isinstance(right, int):
            right = str(right)
        else:
            right = f'"{right}"'
        return f"{left} = {right}"
    if "neq" in expr:
        left, right = expr["neq"]
        if isinstance(left, dict) and left.get("var"):
            left = left["var"]
        if isinstance(right, bool):
            right = str(right).upper()
        elif isinstance(right, int):
            right = str(right)
        else:
            right = f'"{right}"'
        return f"{left} /= {right}"
    if "in" in expr:
        left, values = expr["in"]
        if isinstance(left, dict) and left.get("var"):
            left = left["var"]
        vals = _format_values(values)
        return f"{left} \\in {{{vals}}}"
    if "and" in expr:
        return " /\\ ".join(f"({_compile_expr(e)})" for e in expr["and"])
    if "or" in expr:
        return " \\/ ".join(f"({_compile_expr(e)})" for e in expr["or"])
    if "not" in expr:
        return f"~({_compile_expr(expr['not'])})"
    raise ValueError(f"Unknown expression: {expr}")


def _format_values(values: list[Any]) -> str:
    """Format list of values for TLA+ set."""
    parts = []
    for v in values:
        if isinstance(v, str):
            parts.append(f'"{v}"')
        elif isinstance(v, bool):
            parts.append(str(v).upper())
        else:
            parts.append(str(v))
    return ", ".join(parts)


def run_tlc(tla_content: str, cfg_content: str) -> dict[str, Any]:
    """Run TLC on generated TLA+ files with timeout and kill."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tla_path = Path(tmpdir) / "Model.tla"
        cfg_path = Path(tmpdir) / "Model.cfg"

        tla_path.write_text(tla_content)
        cfg_path.write_text(cfg_content)

        cmd = [
            "java",
            "-cp",
            str(TLA_TOOLS_JAR),
            "tlc2.TLC",
            "-workers",
            "auto",
            "-maxSetSize",
            str(STATE_LIMIT),
            "-config",
            str(cfg_path),
            str(tla_path),
        ]

        start = time.time()
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        try:
            stdout, stderr = proc.communicate(timeout=CHECK_TIMEOUT_SECONDS)
            duration_ms = int((time.time() - start) * 1000)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.terminate()
            raise TLCError("Model checking timed out", returncode=-1, stderr="TIMEOUT") from None

        return _parse_tlc_output(stdout, stderr, proc.returncode, duration_ms)


def _parse_tlc_output(
    stdout: str, stderr: str, returncode: int, duration_ms: int
) -> dict[str, Any]:
    """Parse TLC output into verification result."""
    if returncode == 0:
        return {
            "status": "PROPERTY_HOLDS",
            "engine": "TLC",
            "engine_version": "TLC 1.7.4",
            "duration_ms": duration_ms,
            "statistics": _extract_stats(stdout),
            "counterexample": None,
        }

    if "Invariant" in stdout or "violated" in stdout.lower():
        return {
            "status": "PROPERTY_VIOLATED",
            "engine": "TLC",
            "engine_version": "TLC 1.7.4",
            "duration_ms": duration_ms,
            "counterexample": _extract_counterexample(stdout),
            "statistics": _extract_stats(stdout),
        }

    if "state space" in stdout.lower() and "exceeded" in stdout.lower():
        return {
            "status": "STATE_LIMIT_REACHED",
            "engine": "TLC",
            "engine_version": "TLC 1.7.4",
            "duration_ms": duration_ms,
            "error_detail": stdout[-2000:],
            "counterexample": None,
            "statistics": _extract_stats(stdout),
        }

    if returncode < 0 or "error" in stderr.lower() or "exception" in stderr.lower():
        return {
            "status": "ENGINE_ERROR",
            "engine": "TLC",
            "engine_version": "TLC 1.7.4",
            "duration_ms": duration_ms,
            "error_detail": stderr or stdout,
            "counterexample": None,
            "statistics": _extract_stats(stdout),
        }

    return {
        "status": "ENGINE_ERROR",
        "engine": "TLC",
        "engine_version": "TLC 1.7.4",
        "duration_ms": duration_ms,
        "error_detail": stdout[-2000:] + stderr[-2000:],
        "counterexample": None,
        "statistics": _extract_stats(stdout),
    }


def _extract_stats(stdout: str) -> dict[str, int]:
    """Extract statistics from TLC output."""
    stats = {}
    for line in stdout.splitlines():
        if "states generated" in line.lower():
            stats["states_generated"] = int(line.split()[-1].replace(",", ""))
        elif "distinct states" in line.lower():
            stats["distinct_states"] = int(line.split()[-1].replace(",", ""))
        elif "depth" in line.lower() and "=" in line:
            stats["depth"] = int(line.split("=")[-1].strip())
    return stats


def _extract_counterexample(stdout: str) -> dict[str, Any] | None:
    """Extract counterexample trace from TLC output.

    TLC trace format:
    State 1: <Initial predicate>
      status = "Created"
      approved = FALSE
      ...
    /Approve
    State 2: <Approve>
      status = "Approved"
      ...
    /Cancel
    State 3: <Cancel>
      ...
    /Execute
    State 4: <Execute>
      ...
    """
    lines = stdout.splitlines()

    state_pattern = re.compile(r"^State\s+(\d+):\s*<(.*)>$")
    trans_pattern = re.compile(r"^/(.+)$")
    assign_pattern = re.compile(r"^\s+(\w+)\s*=\s*(.+)$")

    states: dict[int, dict[str, Any]] = {}
    transitions: dict[int, str] = {}

    current_state_num: int | None = None
    current_transition: str | None = None

    for line in lines:
        state_match = state_pattern.match(line)
        if state_match:
            current_state_num = int(state_match.group(1))
            states[current_state_num] = {}
            continue

        if current_state_num is not None:
            trans_match = trans_pattern.match(line)
            if trans_match:
                current_transition = trans_match.group(1).strip()
                transitions[current_state_num + 1] = current_transition
                continue

            assign_match = assign_pattern.match(line)
            if assign_match:
                var_name = assign_match.group(1)
                var_value = assign_match.group(2).strip().strip('"')
                if var_value.upper() == "TRUE":
                    var_value = True
                elif var_value.upper() == "FALSE":
                    var_value = False
                elif var_value.isdigit() or (var_value.startswith("-") and var_value[1:].isdigit()):
                    var_value = int(var_value)
                states[current_state_num][var_name] = var_value
                continue

    if not states:
        return None

    steps = []
    sorted_state_nums = sorted(states.keys())
    for i, state_num in enumerate(sorted_state_nums):
        step = {
            "number": i,
            "state": states[state_num],
        }
        if i > 0:
            step["transition"] = transitions.get(state_num)
        steps.append(step)

    return {"steps": steps} if steps else None
