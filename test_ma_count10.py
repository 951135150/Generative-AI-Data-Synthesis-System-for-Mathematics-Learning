"""Test multi-agent synthesis with count=10."""
import asyncio
import json
import sys
import os
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(name)s - %(message)s')

sys.path.insert(0, os.path.dirname(__file__))

from src.multi_agent.coordinator import Coordinator, SynthesisConfig


async def main():
    config = SynthesisConfig(
        topics=["Derivatives"],
        target_count=10,
        mode="drill",
        difficulty=3,
        question_type="calculation",
        timeout_seconds=2400.0,
    )
    print(f"\n=== Starting multi-agent synthesis: target_count={config.target_count} ===\n")

    coordinator = Coordinator(config)
    result = await coordinator.synthesize()

    print(f"\n=== Synthesis Complete ===")
    print(f"Success: {result.success}")
    print(f"Total problems: {result.total_problems}")
    print(f"Terminated by: {result.terminated_by}")
    print(f"Duration: {result.duration_seconds:.1f}s")
    print(f"LLM calls: {result.total_llm_calls}")
    print(f"Agent messages: {result.total_agent_messages}")
    print(f"Statistics: {json.dumps(result.statistics, indent=2, ensure_ascii=False)}")

    if result.error:
        print(f"Error: {result.error}")

    # Validate
    print(f"\n=== Validation ===")
    print(f"Expected: 10 problems, Got: {result.total_problems}")
    if result.total_problems == 10:
        print("PASS: Correct number of problems generated.")
    else:
        print(f"FAIL: Expected 10, got {result.total_problems}")

    # Show problem summaries
    print(f"\n=== Problem Summaries ===")
    for i, p in enumerate(result.problems):
        pid = p.get("id", "unknown")
        topic = p.get("topic", "unknown")
        qtype = p.get("question_type", "unknown")
        diff = p.get("difficulty", "?")
        print(f"  {i+1}. [{pid}] topic={topic}, type={qtype}, difficulty={diff}")

    # Save final report
    report_path = os.path.join(os.path.dirname(__file__), "output", "count10_test_report.json")
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({
            "config": config.to_dict(),
            "success": result.success,
            "total_problems": result.total_problems,
            "statistics": result.statistics,
            "duration_seconds": result.duration_seconds,
            "total_llm_calls": result.total_llm_calls,
            "terminated_by": result.terminated_by,
            "problem_ids": [p.get("id") for p in result.problems],
        }, f, ensure_ascii=False, indent=2)
    print(f"\nReport saved to: {report_path}")


if __name__ == "__main__":
    asyncio.run(main())
