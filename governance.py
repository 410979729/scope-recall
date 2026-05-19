from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .gating import compact_text, dedup_key
from .scoring import semantic_similarity

_SENTENCE_RE = re.compile(r"(?<=[.!?。！？])\s+")
_PREFERENCE_RE = re.compile(
    r"\b(?P<subject>[A-Z][\w-]*|user|joy)\s+(?:prefers?|likes?|wants?|希望|喜欢|喜歡|偏好)\s+(?P<object>[^.!?。！？]+)",
    re.IGNORECASE,
)
_DEPLOY_RE = re.compile(
    r"\b(?:(?:the\s+)?(?:current\s+)?(?:production|prod)\s+)?(?:deploy|deployment|rollout|release)\s+(?:command\s+)?(?:is|uses?|=)\s+(?P<command>[^.!?。！？]+)",
    re.IGNORECASE,
)
_IDENTITY_RE = re.compile(r"\b(?P<subject>[A-Z][\w-]*)\s+is\s+(?P<object>[^.!?。！？]+)", re.IGNORECASE)
_NEGATION_RE = re.compile(r"\b(no longer|not|never|不再|不要|不是|取消|avoid|stop)\b", re.IGNORECASE)


@dataclass
class ExtractionCandidate:
    content: str
    target: str
    category: str
    confidence: float


def split_sentences(text: str) -> list[str]:
    cleaned = (text or "").strip()
    if not cleaned:
        return []
    parts = _SENTENCE_RE.split(cleaned)
    output: list[str] = []
    for part in parts:
        for sub in re.split(r"[\n;；]+", part):
            sub = sub.strip()
            if sub:
                output.append(sub)
    return output


def _unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        clean = str(value or "").strip().lower()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        output.append(clean)
    return output


def _authority_for_source(source: str = "") -> str:
    normalized = str(source or "").strip().lower()
    if normalized == "tool-store" or normalized.startswith("tool"):
        return "agent_tool"
    if normalized == "turn-user":
        return "user_turn"
    if normalized == "turn-extracted":
        return "rule_extracted"
    if normalized.startswith("legacy"):
        return "legacy_import"
    if normalized == "builtin-curated":
        return "curated_memory"
    return "unknown"


def classify_memory(text: str, target: str = "memory", source: str = "") -> dict[str, Any]:
    lowered = (text or "").lower()
    normalized_target = str(target or "memory").strip().lower()
    category = "general"
    tier = "working"
    kind = "semantic_fact"
    lifecycle = "promoted"
    sensitivity = "normal"
    confidence = 0.55
    expires_at = None
    authority = _authority_for_source(source)

    if normalized_target == "general":
        category = "general"
        tier = "working"
        kind = "raw_observation"
        lifecycle = "scratch"
        confidence = 0.5
    elif normalized_target == "user" or any(word in lowered for word in ("prefer", "prefers", "likes", "wants", "希望", "喜欢", "偏好")):
        category = "preference"
        tier = "core"
        kind = "user_preference"
        confidence = 0.86
    elif normalized_target == "ops" or any(word in lowered for word in ("deploy", "rollout", "restart", "gateway", "command", "production", "prod")):
        category = "procedure"
        tier = "core"
        kind = "ops_procedure"
        confidence = 0.8
    elif normalized_target == "project":
        category = "project"
        tier = "core"
        kind = "project_fact"
        confidence = 0.78
    elif normalized_target == "memory":
        category = "fact"
        tier = "core"
        kind = "environment_fact"
        confidence = 0.72

    if any(word in lowered for word in ("temporary", "temp", "one-off", "scratch", "临时", "一次性")):
        tier = "working"
        if normalized_target == "general":
            kind = "raw_observation"
            lifecycle = "scratch"
        else:
            kind = "temporary_state"
            lifecycle = "candidate"
        expires_at = "stale-review"
        confidence = min(confidence, 0.62)
    if any(word in lowered for word in ("token", "password", "secret", "api key", "apikey")):
        sensitivity = "sensitive"

    tags = _unique_strings([f"target:{normalized_target}", f"kind:{kind}", f"source:{source or 'unknown'}"])
    scope_mode = "local" if normalized_target == "general" else "shared"
    return {
        "category": category,
        "tier": tier,
        "kind": kind,
        "lifecycle": lifecycle,
        "authority": authority,
        "confidence": confidence,
        "sensitivity": sensitivity,
        "expires_at": expires_at,
        "entities": [],
        "tags": tags,
        "scope_mode": scope_mode,
    }


def extract_candidates(text: str) -> list[ExtractionCandidate]:
    candidates: list[ExtractionCandidate] = []
    for sentence in split_sentences(text):
        stripped = sentence.strip().rstrip(".!?。！？")
        if not stripped:
            continue
        pref = _PREFERENCE_RE.search(stripped)
        if pref:
            subject = pref.group("subject").strip()
            obj = pref.group("object").strip()
            candidates.append(
                ExtractionCandidate(
                    content=compact_text(f"{subject} prefers {obj}.", 360),
                    target="user",
                    category="preference",
                    confidence=0.86,
                )
            )
            continue
        deploy = _DEPLOY_RE.search(stripped)
        if deploy:
            command = deploy.group("command").strip()
            candidates.append(
                ExtractionCandidate(
                    content=compact_text(f"Production deploy command is {command}.", 360),
                    target="ops",
                    category="procedure",
                    confidence=0.82,
                )
            )
            continue
        identity = _IDENTITY_RE.search(stripped)
        if identity and len(stripped.split()) <= 18:
            candidates.append(
                ExtractionCandidate(
                    content=compact_text(stripped + ".", 360),
                    target="project",
                    category="fact",
                    confidence=0.68,
                )
            )
    return candidates


def is_conflicting(existing: str, candidate: str) -> bool:
    if dedup_key(existing) == dedup_key(candidate):
        return False
    if semantic_similarity(existing, candidate) < 0.35:
        return False
    return bool(_NEGATION_RE.search(existing or "")) != bool(_NEGATION_RE.search(candidate or ""))


def merge_memory_text(existing: str, candidate: str) -> str:
    existing = (existing or "").strip()
    candidate = (candidate or "").strip()
    if not existing:
        return candidate
    if not candidate:
        return existing
    if dedup_key(existing) == dedup_key(candidate):
        return existing
    if candidate.lower() in existing.lower():
        return existing
    if existing.lower() in candidate.lower():
        return candidate
    return compact_text(f"{existing.rstrip('.。')} / {candidate.rstrip('.。')}.", 900)
