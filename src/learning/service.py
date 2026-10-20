import json
import threading
from uuid import uuid4
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text

from src.database import get_database
from src.database.models import AttemptReceipt, EvidenceSnapshot, LearningEvent, Submission, TopicMastery
from src.rag.service import digest

_write_lock = threading.RLock()


class AttemptConflict(ValueError):
    pass


class LearningService:
    def __init__(self, database=None):
        self.database = database or get_database()

    def lookup(self, scope, request_key, request_hash):
        if not request_key:
            return None
        with self.database.session() as session:
            receipt = session.scalar(select(AttemptReceipt).where(
                AttemptReceipt.user_scope == scope, AttemptReceipt.request_key == request_key))
            if receipt:
                if receipt.request_hash != request_hash:
                    raise AttemptConflict("This attempt ID was already used for different content.")
                return json.loads(receipt.response_json)

    def concept_summary(self, user_id):
        """Describe observed attempts; do not label a percentage as latent mastery."""
        with self.database.session() as session:
            receipts = session.scalars(select(AttemptReceipt).where(AttemptReceipt.user_scope == user_id))
            totals = {}
            for receipt in receipts:
                response = json.loads(receipt.response_json)
                if response.get("learning_credit") != "first_attempt":
                    continue
                for concept in response.get("concept_ids", []):
                    state = totals.setdefault(concept, {"concept_id": concept, "attempts": 0, "correct": 0})
                    state["attempts"] += 1
                    state["correct"] += int(response.get("is_correct") is True)
            return [{**state, "observed_accuracy": round(state["correct"] / state["attempts"], 3),
                     "evidence_status": "limited" if state["attempts"] < 3 else "observed_attempts"}
                    for state in sorted(totals.values(), key=lambda s: (s["correct"] / s["attempts"], s["concept_id"]))]

    def save(self, *, user_id, request_key, request_hash, problem, response, evidence, text_answer):
        scope = user_id or "anonymous"
        request_key = request_key or uuid4().hex
        with _write_lock, self.database.session() as session:
            # Serialize read-modify-write in SQLite even across separate worker processes.
            if self.database.engine.dialect.name == "sqlite":
                session.execute(text("BEGIN IMMEDIATE"))
            receipt = session.scalar(select(AttemptReceipt).where(
                AttemptReceipt.user_scope == scope, AttemptReceipt.request_key == request_key))
            if receipt:
                if receipt.request_hash != request_hash:
                    raise AttemptConflict("This attempt ID was already used for different content.")
                return json.loads(receipt.response_json)
            submission_id = f"sub_{uuid4().hex}"
            topic = problem.get("topic", "Unknown")
            if evidence.get("bundle_id") and session.get(EvidenceSnapshot, evidence["bundle_id"]) is None:
                session.add(EvidenceSnapshot(bundle_id=evidence["bundle_id"], index_version=evidence["index_version"],
                                             purpose=evidence["purpose"], payload_json=json.dumps(evidence, ensure_ascii=False)))
            session.add(Submission(
                submission_id=submission_id, user_id=user_id, problem_id=problem.get("problem_id") or problem["id"],
                topic=topic, input_type="text", score=response["logic_alignment_score"],
                is_correct=response["is_correct"], ocr_text=text_answer,
                error_type="reference_mismatch" if not response["is_correct"] else None,
                tutor_feedback=response["tutor_feedback"], next_step=response["next_hint"],
            ))
            first_attempt = not session.scalar(select(Submission.submission_id).where(
                Submission.user_id == user_id, Submission.problem_id == (problem.get("problem_id") or problem["id"])
            ).limit(1)) if user_id else False
            if user_id and first_attempt:
                mastery = session.scalar(select(TopicMastery).where(
                    TopicMastery.user_id == user_id, TopicMastery.topic == topic).with_for_update())
                if mastery is None:
                    raise ValueError("The submitted topic is not in this learner's curriculum.")
                old_count = mastery.completed_count
                score = max(0, min(100, float(response["logic_alignment_score"])))
                # Preserve the original EMA baseline. Promotion requires several independent attempts.
                mastery.mastery_score = round(.4 * mastery.mastery_score + .6 * score / 100, 2)
                mastery.completed_count += 1
                if old_count >= 2 and response["is_correct"] and mastery.mastery_score >= .8:
                    mastery.current_level = min(3, mastery.current_level + 1)
                session.add(LearningEvent(user_id=user_id, topic=topic, score=score,
                                           is_correct=response["is_correct"], level_at_time=mastery.current_level))
            response = {**response, "submission_id": submission_id, "attempt_id": request_key,
                        "progress_recorded": bool(user_id and first_attempt), "problem_version": digest(problem),
                        "learning_credit": "first_attempt" if first_attempt else "retry_no_extra_credit",
                        "concept_ids": problem.get("concept_ids", []),
                        "diagnostic_status": "insufficient_for_misconception_diagnosis",
                        "ai_mode": problem.get("ai_mode", response.get("ai_mode", "unknown"))}
            session.add(AttemptReceipt(receipt_id=submission_id, user_scope=scope,
                                       request_key=request_key, request_hash=request_hash,
                                       response_json=json.dumps(response, ensure_ascii=False)))
            return response


def review_schedule(progress, now=None):
    """A transparent 3/7/14-day practice rule, not a fitted forgetting model."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    events = {}
    for event in progress.get("learning_history", []):
        try:
            at = datetime.fromisoformat(str(event.get("time", "")).replace("Z", "+00:00"))
            at = at.replace(tzinfo=timezone.utc) if at.tzinfo is None else at
        except (TypeError, ValueError):
            continue
        if at > now:
            continue
        events.setdefault(event["topic"], []).append((at, event))
    due = []
    for topic, history in events.items():
        state = progress.get("topics_status", {}).get(topic, {})
        if state.get("completed_count", 0) < 3:
            continue
        history.sort(key=lambda item: item[0])
        last_at, latest = history[-1]
        if not latest.get("is_correct") or float(latest.get("score", 0)) < 80:
            continue
        streak = 0
        for _, event in reversed(history):
            if event.get("is_correct") and float(event.get("score", 0)) >= 80:
                streak += 1
            else:
                break
        interval = 14 if streak >= 5 else 7 if streak >= 3 else 3
        due_at = last_at + timedelta(days=interval)
        if due_at <= now:
            due.append({"topic": topic, "last_practiced_at": last_at.isoformat(),
                        "due_at": due_at.isoformat(), "interval_days": interval,
                        "overdue_days": (now - due_at).days,
                        "reason": f"Review this topic after {interval} days; the interval follows recorded correct attempts."})
    return sorted(due, key=lambda row: (row["due_at"], row["topic"]))


def recommend(progress, retriever, allowed_topics=None, concept_evidence=None, now=None):
    """Transparent rules; scores are not calibrated probabilities of mastery."""
    topics = progress.get("topics_status", {})
    history = progress.get("learning_history", [])
    latest = {e["topic"]: e for e in history}
    choices = []
    due = {item["topic"]: item for item in review_schedule(progress, now)}
    concept_evidence = concept_evidence or []
    for topic, state in topics.items():
        if allowed_topics is not None and topic not in allowed_topics:
            continue
        count = state.get("completed_count", 0)
        mastery = state.get("mastery_score", 0)
        recent = latest.get(topic)
        error_bonus = .2 if recent and not recent["is_correct"] else 0
        priority = 1 - mastery + error_bonus
        if topic in due:
            priority += min(.6, .15 + due[topic]["overdue_days"] / 60)
        weak_concepts = [c for c in concept_evidence if c["attempts"] >= 3 and c["observed_accuracy"] < .6
                         and any(c["concept_id"] in chunk.get("concepts", []) and chunk["topic"] == topic
                                 for chunk in retriever.chunks)]
        if weak_concepts:
            priority += .15
        if count == 0:
            priority += .05
        choices.append((priority, topic, state))
    if not choices:
        return None
    _, topic, state = max(choices, key=lambda x: x[0])
    # Concept links are reviewed course structure, not an inferred student diagnosis.
    related = [c for c in retriever.chunks if c["topic"] == topic]
    for chunk in related:
        for prerequisite in chunk.get("prerequisites", []):
            source = retriever.get_chunk(prerequisite)
            prior = topics.get(source["topic"], {}) if source else {}
            if (source and (allowed_topics is None or source["topic"] in allowed_topics)
                    and prior.get("completed_count", 0) >= 3 and prior.get("mastery_score", 0) < .5):
                return {"topic": source["topic"], "difficulty": 2, "mode": "drill",
                        "reason": f"Review this prerequisite before continuing with {topic}.",
                        "basis": "prerequisite_rule", "concept_ids": source.get("concepts", [])}
    count = state.get("completed_count", 0)
    reason = "No recorded attempts yet; start with a diagnostic exercise." if count == 0 else (
        f"Recorded mastery is {round(state['mastery_score'] * 100)}% across {count} attempts. "
        "Practice this topic before increasing difficulty."
    )
    weak = [c for c in concept_evidence if c["attempts"] >= 3 and c["observed_accuracy"] < .6
            and any(c["concept_id"] in chunk.get("concepts", []) for chunk in related)]
    if weak:
        reason += " Recent independent attempts suggest reviewing " + ", ".join(c["concept_id"].replace("_", " ") for c in weak) + "."
    if topic in due:
        reason += " " + due[topic]["reason"]
    return {"topic": topic, "difficulty": 2 if state.get("mastery_score", 0) < .6 else 3,
            "mode": "drill", "reason": reason, "basis": "spaced_review_rule" if topic in due else "topic_evidence_rule",
            "concept_ids": list(dict.fromkeys(k for c in related for k in c.get("concepts", [])))}
