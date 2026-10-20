"""Repeat the same complete learner scenarios in the network-blocked test suite."""
import pytest
from fastapi.testclient import TestClient

import api_server
from scripts.simulate_students import PROFILES, QUESTION_TYPES, run_profile
from src.simulation import SIMULATION_TOPICS


@pytest.mark.parametrize("profile", PROFILES)
def test_complete_learning_profile_covers_all_topics_and_formats(profile):
    result = run_profile(TestClient(api_server.app), api_server.problem_repository, profile)
    expected = {(topic, kind) for topic in SIMULATION_TOPICS for kind in QUESTION_TYPES}
    assert {(a["topic"], a["question_type"]) for a in result["attempts"]} == expected
    assert result["topics_covered"] == 13
    assert len(result["attempts"]) == 39
    assert result["final_independent_attempts"] == 40
    assert result["fresh_request_retries_without_credit"] == 13
    assert result["adaptive_followup"]["graded"]
    assert all(r["all_topic_states_verified"] for r in result["rounds"])
