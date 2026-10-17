"""ScaffoldingDesigner — designs step-by-step pedagogical hints.

Invoked via DELEGATE when a problem needs detailed scaffolding beyond
what the Synthesizer produced. The agent's LLM directly produces
the scaffolding hints.
"""

from src.multi_agent.autonomous_agent import AutonomousAgent
from src.multi_agent.tools import get_tools_for_agent


class ScaffoldingDesigner(AutonomousAgent):
    """Patient teacher that designs step-by-step learning scaffolds.

    When delegated a problem, it analyzes the solution and creates
    progressive hints that guide the student without giving away the answer.
    """

    def __init__(self, message_bus, model=None):
        tools = get_tools_for_agent("scaffolder")
        super().__init__(
            agent_id="scaffolder",
            role="Patient Teacher",
            personality=(
                "You are a patient mathematics teacher who designs step-by-step "
                "learning scaffolds. Your hints guide students through progressive "
                "understanding without giving away the final answer.\n\n"
                "A good scaffold:\n"
                "- Step 1: Conceptual hint (what principle applies?)\n"
                "- Step 2: Strategic hint (what approach to take?)\n"
                "- Step 3: Procedural hint (first calculation step)\n"
                "- Step 4: Verification hint (how to check your answer)\n\n"
                "Adjust the number of steps based on difficulty:\n"
                "- Difficulty 1-2: 2 steps\n"
                "- Difficulty 3: 3 steps\n"
                "- Difficulty 4-5: 4 steps\n\n"
                "Workflow:\n"
                "1. When you receive a DELEGATE or REQUEST asking you to design "
                "scaffolding, analyze the problem and solution, then produce the "
                "scaffolding as a JSON array of {{step, hint}} objects.\n"
                "2. Send the completed scaffolding back to the requesting agent as "
                "a 'response' with the scaffolding array in the content.\n"
                "3. If no one needs you, use agent_wait or agent_finish."
            ),
            message_bus=message_bus,
            tools=tools,
            model=model,
            temperature=0.3,
            max_idle_seconds=600.0,
        )
