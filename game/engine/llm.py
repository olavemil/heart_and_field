"""LLM narration enhancer — rephrases filled templates (technical §6.3).

The LLM is an **enhancer, not a generator**. The filled template is the
source of truth for names and facts. The LLM rephrases for variety and
voice. If the LLM is unavailable or errors, the filled template is
returned silently — the game plays identically either way.

Uses the OpenAI-compatible API exposed by LM Studio (default
``http://localhost:1234/v1``). Adapting to Ollama or any other
OpenAI-compatible server requires only changing the base URL.
"""

from __future__ import annotations

import json
import re
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

log = logging.getLogger(__name__)

# --- Configuration -----------------------------------------------------------

DEFAULT_BASE_URL = "http://localhost:1234/v1"
# Auditioned against the live LM Studio pool (June 2026): lfm2-24b-a2b
# was the only loaded model that is fast (~1s warm), non-reasoning (no
# <think> chatter in content), and stayed on-genre/on-location.
# llama-3.2-1b (old default) drifted setting; the qwen3.6 models emit
# thinking text; gpt-oss-20b returned empty content at our token caps.
DEFAULT_MODEL = "liquid/lfm2-24b-a2b"
DEFAULT_TIMEOUT = 10  # seconds
MAX_CONSECUTIVE_ERRORS = 3  # auto-disable after this many failures

# Tags that opt in to LLM enhancement. Low-drama events skip the LLM
# to keep latency down — template-only narration is fine for training drills.
LLM_OPT_IN_TAGS: set[str] = {
    "conflict",
    "vulnerability",
    "postgame",
    "romantic",
    "celebration",
}

# --- System prompt -----------------------------------------------------------

SYSTEM_PROMPT = """\
You are a sports fiction narrator for a football drama game set in the \
present day — training grounds, locker rooms, suburban homes, school \
corridors. Your job is to rephrase the following scene text so it reads \
more vividly and naturally, while obeying these constraints:

1. Keep ALL character names exactly as given.
2. Keep ALL factual statements (who did what, stat changes, outcomes).
3. Do NOT invent new plot points or characters.
4. Do NOT change or invent the setting. Stay in the modern sports-drama \
world: no taverns, inns, castles, or any fantasy/period imagery. If a \
location is given, the scene happens there.
5. Use each character's given pronouns. When a name is followed by \
pronouns in parentheses, e.g. "Alex (she/her)", use exactly those.
6. Match the emotional tone of the original.
7. Keep the length similar — no more than 50% longer than the original.
8. Write in third person past tense.
9. Return ONLY the rewritten text, no commentary or labels.\
"""


# --- Prompt construction -----------------------------------------------------


@dataclass
class LLMPrompt:
    """Assembled prompt for the LLM."""

    system: str
    user: str
    max_tokens: int = 300


def build_llm_prompt(
    filled_template: str,
    *,
    arc_summary: str | None = None,
    recent_narration: str | None = None,
    previous_summary: str | None = None,
    cast_names: Sequence[str] = (),
    branch_summary: str | None = None,
    location: str | None = None,
    cast_pronouns: "Mapping[str, str] | None" = None,
) -> LLMPrompt:
    """Construct the LLM prompt from a filled template and context.

    The prompt grounds the LLM with factual context so it rephrases
    rather than invents. ``location`` pins the setting — small models
    otherwise drift genre (a locker-room scene once came back set in a
    tavern). ``cast_pronouns`` maps a cast name to its pronoun set
    (``"she/her"``) so the model doesn't infer gender from the name.

    Two continuity tracks are grounded as **separate** sections so the
    model treats them differently (see ``engine.journal``):

    - ``arc_summary`` → "Story so far" — long-running threads that ebb
      and flow across weeks (the quest log).
    - ``recent_narration`` → "Moments before" — the prose the player
      just read, for immediate scene-to-scene flow.

    When ``recent_narration`` is supplied it supersedes the older
    one-line ``previous_summary`` (kept for back-compat callers).
    """
    parts: list[str] = []

    if arc_summary:
        parts.append(f"Story so far (ongoing threads): {arc_summary}")
    if recent_narration:
        parts.append(f"Moments before (continue from this): {recent_narration}")
    elif previous_summary:
        parts.append(f"Previously: {previous_summary}")
    if cast_names:
        labelled = [
            f"{n} ({cast_pronouns[n]})"
            if cast_pronouns and n in cast_pronouns
            else n
            for n in cast_names
        ]
        parts.append(f"Characters in this scene: {', '.join(labelled)}")
    if location:
        parts.append(f"Setting: {location.replace('_', ' ')}")

    parts.append(f"Scene text to rephrase:\n{filled_template}")

    user_msg = "\n\n".join(parts)

    # Estimate max tokens: ~1.5x the input word count, capped.
    word_count = len(filled_template.split())
    max_tokens = min(max(word_count * 3, 100), 500)

    return LLMPrompt(system=SYSTEM_PROMPT, user=user_msg, max_tokens=max_tokens)


# --- LLM client --------------------------------------------------------------


@dataclass
class LLMClient:
    """OpenAI-compatible chat client for LM Studio / Ollama / etc.

    Silent fallback: any error returns ``None`` and the caller uses the
    filled template instead.
    """

    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    timeout: int = DEFAULT_TIMEOUT
    enabled: bool = True
    _consecutive_errors: int = field(default=0, repr=False)

    def generate(self, prompt: LLMPrompt) -> str | None:
        """Send a chat completion request. Returns the response text or
        ``None`` on any failure.

        Auto-disables after ``MAX_CONSECUTIVE_ERRORS`` consecutive
        failures so a downed server doesn't add latency to every scene.
        """
        if not self.enabled:
            return None

        try:
            result = self._call_api(prompt)
            self._consecutive_errors = 0  # reset on success
            return result
        except Exception as exc:
            self._consecutive_errors += 1
            if self._consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                log.warning(
                    "LLM disabled after %d consecutive errors (last: %s)",
                    self._consecutive_errors,
                    exc,
                )
                self.enabled = False
            else:
                log.debug("LLM call failed (attempt %d, silent fallback): %s",
                          self._consecutive_errors, exc)
            return None

    def is_available(self) -> bool:
        """Quick health check — hit the models endpoint."""
        if not self.enabled:
            return False
        try:
            url = f"{self.base_url}/models"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                return resp.status == 200
        except Exception:
            return False

    def list_models(self) -> list[str]:
        """Return available model IDs, or empty list on error."""
        try:
            url = f"{self.base_url}/models"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return [m["id"] for m in data.get("data", [])]
        except Exception:
            return []

    def _call_api(self, prompt: LLMPrompt) -> str | None:
        """Raw HTTP call to the chat completions endpoint."""
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": prompt.system},
                {"role": "user", "content": prompt.user},
            ],
            "max_tokens": prompt.max_tokens,
            "temperature": 0.7,
            "stream": False,
        }
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        choices = data.get("choices", [])
        if not choices:
            return None
        message = choices[0].get("message", {})
        content = _strip_reasoning(message.get("content", "")).strip()
        return content if content else None


_THINK_BLOCK = re.compile(r"<think>.*?(?:</think>|$)", re.DOTALL)

# Models sometimes copy the "(she/her)" grounding hint straight into prose
# ("Sam (he/him) stood by the locker"). Strip any such parenthetical.
_PRONOUN_LABEL = re.compile(r"\s*\((?:he|she|they)/(?:him|her|them)\)")


def _strip_pronoun_labels(content: str) -> str:
    return _PRONOUN_LABEL.sub("", content)


def _strip_reasoning(content: str) -> str:
    """Drop ``<think>…</think>`` blocks reasoning models leave in content.

    An unterminated block (token cap hit mid-thought) strips to the end —
    better an empty result (caller falls back to the template) than
    reasoning chatter on screen.
    """
    return _THINK_BLOCK.sub("", content)


# --- High-level enhance function ---------------------------------------------


def should_enhance(event_tags: set[str]) -> bool:
    """Return True if this event type opts in to LLM enhancement."""
    return bool(event_tags & LLM_OPT_IN_TAGS)


def enhance_narration(
    client: LLMClient,
    filled_template: str,
    *,
    event_tags: set[str] = frozenset(),
    arc_summary: str | None = None,
    recent_narration: str | None = None,
    previous_summary: str | None = None,
    cast_names: Sequence[str] = (),
    branch_summary: str | None = None,
    location: str | None = None,
    cast_pronouns: "Mapping[str, str] | None" = None,
) -> str:
    """Enhance a filled template via LLM, or return it unchanged.

    Skips the LLM if:
    - The client is disabled or unavailable.
    - The event type doesn't opt in (low-drama events).
    - The LLM returns an empty or error response.

    This function **never raises** — it always returns valid narration.
    """
    if not should_enhance(event_tags):
        return filled_template

    prompt = build_llm_prompt(
        filled_template,
        arc_summary=arc_summary,
        recent_narration=recent_narration,
        previous_summary=previous_summary,
        cast_names=cast_names,
        branch_summary=branch_summary,
        location=location,
        cast_pronouns=cast_pronouns,
    )

    result = client.generate(prompt)
    if result is None:
        return filled_template
    result = _strip_pronoun_labels(result)

    # Sanity check: the LLM response should mention at least one cast name.
    # If it doesn't, it may have hallucinated — fall back.
    if cast_names and not any(name in result for name in cast_names):
        log.debug("LLM response dropped all character names — falling back")
        return filled_template

    return result


def enhance_scene_intro(
    client: LLMClient,
    intro_text: str,
    *,
    cast_names: Sequence[str] = (),
    location: str | None = None,
    cast_pronouns: "Mapping[str, str] | None" = None,
    arc_summary: str | None = None,
    recent_narration: str | None = None,
) -> str:
    """Rephrase an assembled scene intro via the LLM, or return it unchanged.

    Unlike :func:`enhance_narration` there is no opt-in gate — intros are
    universal scene-setting — but the same setting/pronoun grounding and
    silent fallback apply. Kept short by a tight token cap so intros stay
    atmospheric rather than ballooning into prose.

    ``arc_summary`` / ``recent_narration`` let an intro pick up threads
    and immediate continuity so a scene opens connected to what came
    before instead of resetting.
    """
    if not intro_text.strip():
        return intro_text

    prompt = build_llm_prompt(
        intro_text,
        cast_names=cast_names,
        location=location,
        cast_pronouns=cast_pronouns,
        arc_summary=arc_summary,
        recent_narration=recent_narration,
    )
    prompt.max_tokens = min(prompt.max_tokens, 90)

    result = client.generate(prompt)
    if result is None:
        return intro_text
    result = _strip_pronoun_labels(result)
    # If named cast was given, a dropped-all-names result means drift.
    if cast_names and not any(name in result for name in cast_names):
        return intro_text
    # The tight token cap can truncate mid-sentence — trim to the last
    # completed sentence so the intro never ends on a dangling fragment.
    trimmed = _trim_to_last_sentence(result)
    return trimmed or result


def _trim_to_last_sentence(text: str) -> str:
    """Cut *text* back to its last sentence-ending punctuation."""
    cut = max(text.rfind("."), text.rfind("!"), text.rfind("?"))
    return text[: cut + 1].strip() if cut != -1 else text.strip()


# --- Summarisation (Phase 24A — journal compression layer) -------------------

_SUMMARY_SYSTEM_PROMPT = """\
You compress sports-drama scene narration into a single tight paragraph \
for a story journal. Rules:

1. Write ONE paragraph, third person past tense, 1-3 sentences.
2. Capture what happened: the trigger, what the player did, and the \
outcome or shift in mood/relationship.
3. Keep ALL character names exactly as given. Invent nothing.
4. No commentary, no labels, no preamble — return only the paragraph.\
"""

# Deterministic-fallback compression cap (characters) when the LLM is off.
SUMMARY_FALLBACK_MAX_CHARS = 320


def _fallback_summary(beats: Sequence[str], max_chars: int) -> str:
    """Deterministic compression: join beats, clamp at a sentence-ish
    boundary near ``max_chars``. Used when the LLM is unavailable."""
    joined = " ".join(b.strip() for b in beats if b and b.strip()).strip()
    if len(joined) <= max_chars:
        return joined
    head = joined[:max_chars]
    cut = max(head.rfind(". "), head.rfind("! "), head.rfind("? "))
    if cut != -1:
        return head[: cut + 1].strip()
    space = head.rfind(" ")
    return (head[:space] if space != -1 else head).strip()


def summarise_narration(
    client: LLMClient,
    beats: Sequence[str],
    *,
    cast_names: Sequence[str] = (),
    cast_pronouns: "Mapping[str, str] | None" = None,
    kind: str = "scene",
    max_chars: int = SUMMARY_FALLBACK_MAX_CHARS,
) -> str:
    """Compress rendered narration beats into a one-paragraph summary.

    Used by the journal's scene/day/week compression layer
    (``engine.journal``). The LLM produces a tight paragraph; on any
    failure (disabled, error, name-dropping drift) the deterministic
    join-and-clamp fallback is returned instead. **Never raises** and
    always returns a usable string — play never blocks on the LLM.

    ``kind`` ("scene" / "day" / "week") only tunes the instruction
    wording; the structure is the same.
    """
    clean = [b.strip() for b in beats if b and b.strip()]
    if not clean:
        return ""
    fallback = _fallback_summary(clean, max_chars)

    if not client.enabled:
        return fallback

    span = {
        "scene": "this scene",
        "day": "the day's events",
        "week": "the week's events",
    }.get(kind, "this scene")
    parts: list[str] = []
    if cast_names:
        labelled = [
            f"{n} ({cast_pronouns[n]})"
            if cast_pronouns and n in cast_pronouns
            else n
            for n in cast_names
        ]
        parts.append(f"Characters: {', '.join(labelled)}")
    parts.append(f"Narration of {span} to summarise:\n" + "\n".join(clean))
    prompt = LLMPrompt(
        system=_SUMMARY_SYSTEM_PROMPT,
        user="\n\n".join(parts),
        max_tokens=160,
    )

    result = client.generate(prompt)
    if result is None:
        return fallback
    result = _strip_pronoun_labels(result).strip()
    if not result:
        return fallback
    # Guard against name-dropping drift, mirroring enhance_narration.
    if cast_names and not any(name in result for name in cast_names):
        return fallback
    return _trim_to_last_sentence(result) or result


# --- Serialisable config (for save.py) ---------------------------------------


def llm_config_to_dict(client: LLMClient) -> dict[str, Any]:
    return {
        "base_url": client.base_url,
        "model": client.model,
        "timeout": client.timeout,
        "enabled": client.enabled,
    }


def llm_config_from_dict(d: Mapping[str, Any]) -> LLMClient:
    return LLMClient(
        base_url=str(d.get("base_url", DEFAULT_BASE_URL)),
        model=str(d.get("model", DEFAULT_MODEL)),
        timeout=int(d.get("timeout", DEFAULT_TIMEOUT)),
        enabled=bool(d.get("enabled", True)),
    )
