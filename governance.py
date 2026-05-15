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


def classify_memory(text: str, target: str = "memory") -> dict[str, Any]:
    lowered = (text or "").lower()
    category = "general"
    tier = "working"
    sensitivity = "normal"
    confidence = 0.55
    expires_at = None
    if target == "user" or any(word in lowered for word in ("prefer", "prefers", "likes", "wants", "希望", "喜欢", "偏好")):
        category = "preference"
        tier = "core"
        confidence = 0.86
    elif target == "ops" or any(word in lowered for word in ("deploy", "rollout", "restart", "gateway", "command", "production", "prod")):
        category = "procedure"
        tier = "core"
        confidence = 0.8
    elif target == "project":
        category = "project"
        tier = "core"
        confidence = 0.78
    if any(word in lowered for word in ("temporary", "temp", "one-off", "scratch", "临时", "一次性")):
        tier = "working"
        expires_at = "stale-review"
        confidence = min(confidence, 0.62)
    if any(word in lowered for word in ("token", "password", "secret", "api key", "apikey")):
        sensitivity = "sensitive"
    return {"category": category, "tier": tier, "confidence": confidence, "sensitivity": sensitivity, "expires_at": expires_at}


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
