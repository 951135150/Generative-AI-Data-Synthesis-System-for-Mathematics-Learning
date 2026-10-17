"""Autonomous agents for the true multi-agent system."""

from src.multi_agent.agents.synthesizer import ProblemSynthesizer
from src.multi_agent.agents.scaffolder import ScaffoldingDesigner
from src.multi_agent.agents.reviewer import QualityReviewer
from src.multi_agent.agents.curator import DatasetCurator

__all__ = [
    "ProblemSynthesizer",
    "ScaffoldingDesigner",
    "QualityReviewer",
    "DatasetCurator",
]
