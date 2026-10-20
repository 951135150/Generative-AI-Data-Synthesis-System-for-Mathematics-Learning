"""Coordinator — lightweight facilitator for the multi-agent system.

Creates agents, starts them concurrently, sends the initial task,
and monitors for completion. The Coordinator does NOT control agent
flow — agents interact autonomously through the MessageBus.
"""

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.config import Config
from src.multi_agent.message_bus import MessageBus
from src.multi_agent.messages import Message, MessageType, Conversation
from src.multi_agent.agents.synthesizer import ProblemSynthesizer
from src.multi_agent.agents.scaffolder import ScaffoldingDesigner
from src.multi_agent.agents.reviewer import QualityReviewer
from src.multi_agent.agents.curator import DatasetCurator
from src.multi_agent.tools import set_session_context

logger = logging.getLogger(__name__)


@dataclass
class SynthesisConfig:
    """Configuration for a synthesis run."""
    topics: List[str]
    target_count: int = 5
    mode: str = "drill"
    difficulty: int = 3
    question_type: str = "calculation"
    timeout_seconds: float = 600.0
    output_dir: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.topics:
            raise ValueError("At least one synthesis topic is required.")
        if not 1 <= self.target_count <= 20:
            raise ValueError("target_count must be between 1 and 20.")
        if self.mode not in {"drill", "exam"}:
            raise ValueError("mode must be drill or exam.")
        if not 1 <= self.difficulty <= 5:
            raise ValueError("difficulty must be between 1 and 5.")
        if self.question_type not in {"calculation", "mcq", "fill_in"}:
            raise ValueError("Unsupported question_type.")

    def to_dict(self) -> dict:
        return {
            "topics": self.topics,
            "target_count": self.target_count,
            "mode": self.mode,
            "difficulty": self.difficulty,
            "question_type": self.question_type,
            "output_dir": self.output_dir,
        }


@dataclass
class SynthesisResult:
    """Results from a synthesis run."""
    success: bool = False
    total_problems: int = 0
    problems: List[Dict] = field(default_factory=list)
    statistics: Dict[str, Any] = field(default_factory=dict)
    conversation_log: List[Dict] = field(default_factory=list)
    total_llm_calls: int = 0
    total_agent_messages: int = 0
    duration_seconds: float = 0.0
    terminated_by: str = ""  # "complete" | "timeout" | "error"
    error: Optional[str] = None


class Coordinator:
    """Facilitates a multi-agent synthesis session.

    Creates all agents, starts them concurrently, sends the initial
    task, and monitors for completion. Agents decide autonomously
    how to collaborate — the Coordinator only observes.
    """

    def __init__(self, config: SynthesisConfig):
        self.config = config
        self.message_bus = MessageBus()
        self.agents: Dict[str, Any] = {}
        self.run_id = f"run_{uuid.uuid4().hex[:12]}"
        self._output_dir = config.output_dir or os.path.join(Config.OUTPUT_DIR, "multi_agent", self.run_id)
        os.makedirs(self._output_dir, exist_ok=True)

        # Set module-level session context so ALL tool calls (even LLM-initiated) use correct directory
        set_session_context(self._output_dir)

    async def synthesize(self) -> SynthesisResult:
        """Run the full multi-agent synthesis session."""
        set_session_context(self._output_dir)
        if Config.AI_MODE == "simulation":
            return await self._simulate_roles()
        start_time = time.time()
        self._session_start_time = start_time  # Track when this session began
        result = SynthesisResult()

        try:
            self._create_agents()

            # Start all agents concurrently
            agent_tasks = [
                asyncio.create_task(agent.run(), name=agent.agent_id)
                for agent in self.agents.values()
            ]

            # Wait for all agents to register with the MessageBus
            while len(self.message_bus.registered_agents) < len(self.agents):
                await asyncio.sleep(0.05)

            # Send initial task
            await self._send_initial_messages()

            # Monitor until completion or timeout
            result = await self._monitor(agent_tasks)

            # Signal all agents to stop
            for agent in self.agents.values():
                agent.running = False

            # Wait briefly for graceful shutdown
            await asyncio.sleep(1)

            # Cancel any tasks still running
            for task in agent_tasks:
                if not task.done():
                    task.cancel()

            await asyncio.gather(*agent_tasks, return_exceptions=True)

        except Exception as e:
            logger.error(f"[Coordinator] Synthesis failed: {e}")
            result.success = False
            result.error = str(e)
            result.terminated_by = "error"

        result.duration_seconds = time.time() - start_time
        result.total_agent_messages = self.message_bus.total_messages
        result.conversation_log = [
            m.to_dict() for m in self._collect_all_messages()
        ]

        # Collect LLM call counts
        for agent in self.agents.values():
            result.total_llm_calls += agent.llm_call_count

        # Collect saved problems
        result.problems = self._collect_problems()
        result.total_problems = len(result.problems)
        result.statistics = self._compute_statistics(result.problems)
        if result.total_problems == 0:
            result.success = False
            result.error = result.error or "No validated problems were produced."
        elif result.total_problems < self.config.target_count:
            result.success = False
            result.error = (
                f"Only {result.total_problems} of {self.config.target_count} "
                "requested problems passed validation."
            )

        # Save final dataset
        self._save_final_dataset(result)

        logger.info(
            f"[Coordinator] Done. Problems: {result.total_problems}, "
            f"LLM calls: {result.total_llm_calls}, "
            f"Duration: {result.duration_seconds:.1f}s, "
            f"Terminated: {result.terminated_by}"
        )

        return result

    async def _simulate_roles(self):
        """Real retrieval/validation/message transport with explicitly scripted role replies."""
        from src.generator import ProblemGenerator
        from src.data_loader import GoldenDataLoader
        from src.rag import get_retriever
        from src.multi_agent.tools import _save_problem_to_disk
        from src.simulation import fixture_review

        start = time.perf_counter()
        result = SynthesisResult(terminated_by="complete")
        for name in ("curator", "synthesizer", "scaffolder", "reviewer"):
            await self.message_bus.register(name)

        async def emit(sender, recipient, content, kind=MessageType.NOTIFY):
            await self.message_bus.send(Message(type=kind, sender=sender, recipient=recipient,
                                                conversation_id=self.run_id,
                                                content={"ai_mode": "simulation", "run_id": self.run_id, **content}))

        generator = ProblemGenerator(GoldenDataLoader(Config.GOLDEN_DATASET_PATH))
        try:
            for index in range(self.config.target_count):
                if time.perf_counter() - start > self.config.timeout_seconds:
                    result.terminated_by = "timeout"
                    break
                topic = self.config.topics[index % len(self.config.topics)]
                await emit("curator", "synthesizer", {"stage": "coverage_plan", "topic": topic,
                                                     "note": "Scripted offline role simulation; no autonomous model reasoning."})
                problem = await asyncio.to_thread(generator.generate_one, [topic], self.config.mode,
                                                   self.config.difficulty, None, self.config.question_type)
                if not problem:
                    await emit("synthesizer", "curator", {"stage": "generation_failed"}, MessageType.ERROR)
                    continue
                await emit("synthesizer", "scaffolder", {"stage": "draft_ready", "problem_id": problem["id"],
                                                           "evidence_bundle_id": problem.get("retrieval", {}).get("bundle_id")})
                # The scaffolder actually adds a separate, answer-free verification prompt.
                problem["scaffolding"].append({"step": 3, "hint": "Check your result using the inverse operation where applicable."})
                await emit("scaffolder", "reviewer", {"stage": "scaffolding_ready", "hint_count": len(problem["scaffolding"])})
                evidence = await asyncio.to_thread(get_retriever().retrieve, topic, topics=[topic], purpose="review")
                review = fixture_review(problem)
                if not review["is_mathematically_correct"]:
                    await emit("reviewer", "synthesizer", {"stage": "rejected", "review": review}, MessageType.REJECT)
                    continue
                problem["review_retrieval"] = evidence
                problem["publishing_status"] = "simulation_checked"
                saved = _save_problem_to_disk(problem, output_dir=self._output_dir)
                if saved["saved"]:
                    result.problems.append(problem)
                    await emit("reviewer", "curator", {"stage": "fixture_checked", "problem_id": problem["id"],
                                                        "review_kind": "deterministic_fixture_check"}, MessageType.APPROVE)
            result.total_problems = len(result.problems)
            result.success = result.total_problems == self.config.target_count
            result.error = None if result.success else "Not all offline fixtures passed."
        except Exception as error:
            result.error, result.terminated_by = str(error), "error"
            await emit("curator", None, {"stage": "failed", "message": str(error)}, MessageType.ERROR)
        result.duration_seconds = time.perf_counter() - start
        result.total_agent_messages = self.message_bus.total_messages
        result.conversation_log = [m.to_dict() for m in self.message_bus.get_all_messages_since(0)]
        result.statistics = self._compute_statistics(result.problems)
        result.statistics["ai_mode"] = "simulation"
        result.statistics["review_kind"] = "deterministic_fixture_check"
        self._save_final_dataset(result)
        return result

    def _create_agents(self) -> None:
        """Instantiate all four agents."""
        self.agents = {
            "synthesizer": ProblemSynthesizer(self.message_bus),
            "scaffolder": ScaffoldingDesigner(self.message_bus),
            "reviewer": QualityReviewer(self.message_bus),
            "curator": DatasetCurator(self.message_bus),
        }

    async def _send_initial_messages(self) -> None:
        """Send the initial task to kick off the synthesis."""
        conv_id = f"synth_{uuid.uuid4().hex[:8]}"

        # Initialize all agents' memory with the config (include session timestamp for filtering)
        config_with_session = self.config.to_dict()
        config_with_session["session_start_time"] = self._session_start_time
        config_with_session["output_dir"] = self._output_dir  # Use coordinator's resolved dir
        for agent in self.agents.values():
            agent.memory.internal_state["synthesis_config"] = config_with_session

        # Send generation request to Synthesizer
        synth_msg = Message(
            type=MessageType.REQUEST,
            sender="coordinator",
            recipient="synthesizer",
            conversation_id=conv_id,
            content={
                "action": "generate_problem",
                "params": {
                    "topics": self.config.topics,
                    "difficulty": self.config.difficulty,
                    "mode": self.config.mode,
                    "question_type": self.config.question_type,
                },
                "target_count": self.config.target_count,
            },
        )
        await self.message_bus.send(synth_msg)

        # Send config to Curator so it knows the target
        curator_msg = Message(
            type=MessageType.NOTIFY,
            sender="coordinator",
            recipient="curator",
            conversation_id=conv_id,
            content={
                "event": "synthesis_started",
                "config": self.config.to_dict(),
            },
        )
        await self.message_bus.send(curator_msg)

        # Also notify the reviewer of the config (for context)
        reviewer_msg = Message(
            type=MessageType.NOTIFY,
            sender="coordinator",
            recipient="reviewer",
            conversation_id=conv_id,
            content={
                "event": "synthesis_config",
                "config": self.config.to_dict(),
            },
        )
        await self.message_bus.send(reviewer_msg)

    async def _monitor(self, agent_tasks: list) -> SynthesisResult:
        """Monitor agent activity until completion or timeout."""
        deadline = time.time() + self.config.timeout_seconds

        while time.time() < deadline:
            # Check for dataset_complete broadcast
            for conv in self.message_bus.get_all_conversations().values():
                for msg in conv.messages:
                    if (
                        msg.type == MessageType.BROADCAST
                        and msg.content.get("event") == "dataset_complete"
                    ):
                        result = SynthesisResult()
                        result.success = True
                        result.terminated_by = "complete"
                        return result

            # Check if all agents have finished (no running agents)
            all_finished = all(not agent.running for agent in self.agents.values())
            if all_finished:
                logger.info("[Coordinator] All agents have finished.")
                result = SynthesisResult()
                result.success = True
                result.terminated_by = "agents_finished"
                return result

            # Check if all agent tasks have completed
            tasks_done = all(task.done() for task in agent_tasks)
            if tasks_done:
                result = SynthesisResult()
                result.success = True
                result.terminated_by = "tasks_completed"
                return result

            await asyncio.sleep(2)

        # Timeout
        logger.warning(f"[Coordinator] Timeout after {self.config.timeout_seconds}s")
        result = SynthesisResult()
        result.success = len(self._collect_problems()) > 0
        result.terminated_by = "timeout"
        return result

    def _collect_all_messages(self) -> list:
        """Collect all messages from all conversations."""
        all_msgs = []
        for conv in self.message_bus.get_all_conversations().values():
            all_msgs.extend(conv.messages)
        return sorted(all_msgs, key=lambda m: m.timestamp)

    def _collect_problems(self) -> list:
        """Collect only problems generated during this synthesis session."""
        problems = []
        if not os.path.exists(self._output_dir):
            return problems

        session_start = getattr(self, '_session_start_time', 0)
        skip_files = {'multi_agent_dataset.json', 'synthesis_metadata.json'}

        for filename in sorted(os.listdir(self._output_dir)):
            if filename in skip_files:
                continue
            if filename.endswith(".json"):
                filepath = os.path.join(self._output_dir, filename)
                # Only collect files created during this session
                try:
                    mtime = os.path.getmtime(filepath)
                    if mtime < session_start:
                        continue
                except OSError:
                    continue
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict):
                        problems.append(data)
                except (json.JSONDecodeError, OSError):
                    pass

        return problems

    def _compute_statistics(self, problems: list) -> dict:
        """Compute summary statistics for the generated dataset."""
        if not problems:
            return {}

        topics = set()
        types = {}
        difficulties = []
        scores = []

        for p in problems:
            if not isinstance(p, dict):
                continue
            topic = p.get("topic", "unknown")
            topics.add(topic)

            qtype = p.get("question_type", "unknown")
            types[qtype] = types.get(qtype, 0) + 1

            diff = p.get("difficulty")
            if diff is not None:
                difficulties.append(diff)

            score = p.get("quality_score")
            if score is not None:
                scores.append(score)

        return {
            "total_problems": len(problems),
            "unique_topics": len(topics),
            "topics_covered": sorted(topics),
            "type_distribution": types,
            "avg_difficulty": sum(difficulties) / len(difficulties) if difficulties else 0,
            "avg_quality_score": sum(scores) / len(scores) if scores else 0,
        }

    def _save_final_dataset(self, result: SynthesisResult) -> None:
        """Save the complete dataset and metadata to disk."""
        dataset_path = os.path.join(self._output_dir, "multi_agent_dataset.json")
        with open(dataset_path, "w", encoding="utf-8") as f:
            json.dump(result.problems, f, ensure_ascii=False, indent=2)

        metadata_path = os.path.join(self._output_dir, "synthesis_metadata.json")
        metadata = {
            "synthesis_id": uuid.uuid4().hex[:12],
            "config": self.config.to_dict(),
            "statistics": result.statistics,
            "total_llm_calls": result.total_llm_calls,
            "total_agent_messages": result.total_agent_messages,
            "duration_seconds": result.duration_seconds,
            "terminated_by": result.terminated_by,
            "success": result.success,
            "error": result.error,
            "agent_conversation_log": result.conversation_log,
        }
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

        logger.info(f"[Coordinator] Dataset saved to {dataset_path}")
        logger.info(f"[Coordinator] Metadata saved to {metadata_path}")
