"""Pure utility tools for multi-agent system.

Tools here perform file I/O and data lookups ONLY.
NO LLM calls inside tool handlers — the agents do the thinking.
"""

import json
import os
import tempfile
import time
import logging
from typing import Any, Dict, List, Optional

from src.config import Config
from src.database import ProblemRepository
from src.multi_agent.autonomous_agent import ToolDefinition
from src.validation import MathematicalValidator

logger = logging.getLogger(__name__)

# ── Module-level session context (set by Coordinator at session start) ──
# This ensures tools use the correct directory even when called via LLM path
# (where the LLM doesn't know to pass output_dir or session_start_time).
_session_output_dir: Optional[str] = None
_session_start_time: float = 0


def set_session_context(output_dir: str) -> None:
    """Set the current session's output directory and start time.
    Called by the Coordinator at the beginning of each synthesis run."""
    global _session_output_dir, _session_start_time
    _session_output_dir = output_dir
    _session_start_time = time.time()
    os.makedirs(output_dir, exist_ok=True)


def _resolve_output_dir(explicit_dir: Optional[str]) -> str:
    """Resolve output directory: explicit arg > session context > config default."""
    return explicit_dir or _session_output_dir or Config.OUTPUT_DIR


def _resolve_session_start(explicit_start: float) -> float:
    """Resolve session start time: explicit arg > session context > 0."""
    return explicit_start or _session_start_time


# ── Tool Handlers (sync, no LLM calls) ────────────────────────


def _save_problem_to_disk(problem_data: dict, output_dir: str = None) -> dict:
    """Save a completed problem to disk. Pure file I/O."""
    validation = MathematicalValidator().validate(problem_data)
    if not validation.passed:
        logger.error(
            "Refusing to save invalid problem: %s",
            "; ".join(validation.issues),
        )
        return {
            "saved": False,
            "status": "validation_failed",
            "issues": validation.issues,
            "validation": validation.to_dict(),
        }

    problem_data = validation.normalized_problem or problem_data
    problem_data["deterministic_validation"] = validation.to_dict()
    directory = _resolve_output_dir(output_dir)
    os.makedirs(directory, exist_ok=True)

    problem_id = problem_data.get("problem_id") or problem_data.get("id", "unknown")
    filename = os.path.join(directory, f"{problem_id}.json")

    # Atomic replacement prevents readers from observing a partially written
    # JSON document when concurrent synthesis requests target the same folder.
    fd, temporary_path = tempfile.mkstemp(
        prefix=f".{problem_id}.",
        suffix=".tmp",
        dir=directory,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(problem_data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary_path, filename)
    except Exception:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)
        raise

    # The JSON artifact remains useful for inspection; SQLite is the runtime
    # source of truth used by the API and evaluation tooling.
    if output_dir is None:
        ProblemRepository().upsert(problem_data, source="multi_agent")

    return {"saved": True, "path": filename, "problem_id": problem_id}


def _get_topic_list(args: dict = None) -> dict:
    """Return all available topics from the data loader."""
    try:
        from src.data_loader import GoldenDataLoader
        loader = GoldenDataLoader()
        topics = loader.get_main_topics()
        return {"topics": topics, "count": len(topics)}
    except Exception as e:
        return {"topics": [], "error": str(e)}


def _get_examples_for_topic(topic: str, num_examples: int = 2) -> dict:
    """Fetch example problems for a given topic from the golden dataset."""
    try:
        from src.data_loader import GoldenDataLoader
        loader = GoldenDataLoader()
        examples = loader.get_examples(topic, num_examples=num_examples)
        return {"examples": examples, "count": len(examples), "topic": topic}
    except Exception as e:
        return {"examples": [], "error": str(e)}


def _get_dataset_coverage(topics: list = None, output_dir: str = None, session_start_time: float = 0) -> dict:
    """Analyze what topics are covered in the generated dataset so far.

    Only counts individual problem files (those with a "problem_statement" field)
    created during the current session (mtime >= session_start_time).
    Skips batch result files, metadata files, and other non-problem JSON files.
    """
    directory = _resolve_output_dir(output_dir)
    effective_start = _resolve_session_start(session_start_time)
    if not os.path.exists(directory):
        return {"covered_topics": [], "problems_per_topic": {}, "total_problems": 0}

    # Files to skip: batch outputs and metadata (not individual problems)
    SKIP_PREFIXES = ("batch_", "generation_history", "synthesis_metadata", "multi_agent_dataset")

    problems_per_topic = {}
    total = 0
    for filename in os.listdir(directory):
        if not filename.endswith(".json"):
            continue
        if filename.startswith(SKIP_PREFIXES):
            continue
        filepath = os.path.join(directory, filename)

        # Only count files created during this session
        try:
            if effective_start and os.path.getmtime(filepath) < effective_start:
                continue
        except OSError:
            continue

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            def _count_one(p: dict):
                nonlocal total
                total += 1
                t = p.get("topic") or p.get("core_topic") or "unknown"
                problems_per_topic[t] = problems_per_topic.get(t, 0) + 1

            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and "problem_statement" in item:
                        _count_one(item)
            elif isinstance(data, dict) and "problem_statement" in data:
                _count_one(data)
        except (json.JSONDecodeError, OSError):
            pass

    covered = list(problems_per_topic.keys())
    return {
        "covered_topics": covered,
        "problems_per_topic": problems_per_topic,
        "total_problems": total,
    }


def _get_dataset_size(output_dir: str = None) -> dict:
    """Return simple count of saved problems."""
    coverage = _get_dataset_coverage(output_dir=output_dir)
    return {"total_problems": coverage["total_problems"]}


def _read_problem_from_disk(problem_id: str, output_dir: str = None) -> dict:
    """Read a specific problem from disk by ID."""
    directory = output_dir or Config.OUTPUT_DIR
    filepath = os.path.join(directory, f"{problem_id}.json")
    if not os.path.exists(filepath):
        return {"error": f"Problem {problem_id} not found"}
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


# ── Tool Wrappers (match handler signature: args -> result) ──


def _handle_save_problem(args: dict) -> dict:
    problem_data = args.get("problem", args)
    output_dir = args.get("output_dir")
    return _save_problem_to_disk(problem_data, output_dir=output_dir)


def _handle_get_topics(args: dict) -> dict:
    return _get_topic_list(args)


def _handle_get_examples(args: dict) -> dict:
    topic = args.get("topic", "Derivatives")
    num = args.get("num_examples", args.get("count", 2))
    return _get_examples_for_topic(topic, num)


def _handle_get_coverage(args: dict) -> dict:
    topics = args.get("topics")
    session_start = args.get("session_start_time", 0)
    output_dir = args.get("output_dir")
    return _get_dataset_coverage(topics, session_start_time=session_start, output_dir=output_dir)


def _handle_get_size(args: dict) -> dict:
    output_dir = args.get("output_dir")
    return _get_dataset_size(output_dir=output_dir)


# ── Tool Definitions ──────────────────────────────────────────

UTILITY_TOOLS = [
    ToolDefinition(
        name="save_problem",
        description="Save a completed problem to disk. Use only after a problem has been approved.",
        parameters={
            "type": "object",
            "properties": {
                "problem": {
                    "type": "object",
                    "description": "The complete problem data to save",
                },
            },
            "required": ["problem"],
        },
        handler=_handle_save_problem,
        agent_scope=["synthesizer", "curator", "reviewer"],
    ),
    ToolDefinition(
        name="get_topics",
        description="Get the list of all available mathematics topics.",
        parameters={
            "type": "object",
            "properties": {},
        },
        handler=_handle_get_topics,
        agent_scope=["synthesizer", "curator", "scaffolder", "reviewer"],
    ),
    ToolDefinition(
        name="get_examples",
        description="Get example problems for a given topic from the golden dataset.",
        parameters={
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Topic name"},
                "count": {"type": "integer", "description": "Number of examples", "default": 2},
            },
            "required": ["topic"],
        },
        handler=_handle_get_examples,
        agent_scope=["synthesizer", "scaffolder", "curator"],
    ),
    ToolDefinition(
        name="check_coverage",
        description="Check which topics are covered in the generated dataset so far. Returns covered_topics, problems_per_topic, and total_problems.",
        parameters={
            "type": "object",
            "properties": {},
        },
        handler=_handle_get_coverage,
        agent_scope=["curator", "reviewer"],
    ),
    ToolDefinition(
        name="get_dataset_size",
        description="Get the current number of saved problems in the dataset.",
        parameters={
            "type": "object",
            "properties": {},
        },
        handler=_handle_get_size,
        agent_scope=["curator", "synthesizer", "reviewer"],
    ),
]


def get_tool_by_name(name: str) -> Optional[ToolDefinition]:
    """Look up a tool definition by name."""
    for tool in UTILITY_TOOLS:
        if tool.name == name:
            return tool
    return None


def get_tools_for_agent(agent_name: str) -> list:
    """Filter tools to those scoped to a specific agent."""
    return [
        t for t in UTILITY_TOOLS
        if agent_name in t.agent_scope
    ]
