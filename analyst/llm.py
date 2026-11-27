"""Model access: OpenAI (or any compatible endpoint), and a replay of recorded replies for tests and CI."""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

import httpx


@dataclass
class Reply:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0


class ModelError(RuntimeError):
    pass


def key_for(messages: list[dict]) -> str:
    """Recordings are matched on the conversation without the system prompt, so editing documentation does not orphan them."""
    turns = [m for m in messages if m["role"] != "system"]
    return hashlib.sha256(json.dumps(turns, sort_keys=True).encode()).hexdigest()[:20]


class OpenAIModel:
    def __init__(self, model: str, record_to: Path | None = None, client: httpx.Client | None = None):
        self.model = model
        self.record_to = record_to
        self.key = os.environ.get("OPENAI_API_KEY", "")
        self.base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.client = client or httpx.Client(timeout=90)
        if not self.key:
            raise ModelError("OPENAI_API_KEY is not set (copy .env.example to .env)")

    def complete(self, messages: list[dict]) -> Reply:
        started = time.monotonic()
        for attempt in range(4):
            try:
                r = self.client.post(f"{self.base}/chat/completions", headers={"Authorization": f"Bearer {self.key}"},
                                     json={"model": self.model, "messages": messages})
            except httpx.HTTPError as exc:
                if attempt == 3:
                    raise ModelError(f"Could not reach the model: {type(exc).__name__}") from exc
            else:
                if r.status_code == 200:
                    break
                if r.status_code not in (429, 500, 502, 503) or attempt == 3:
                    raise ModelError(f"The model API answered {r.status_code}: {r.json().get('error', {}).get('message', '')[:200]}")
            time.sleep(2 ** attempt)
        data = r.json()
        usage = data.get("usage") or {}
        reply = Reply(data["choices"][0]["message"]["content"] or "", usage.get("prompt_tokens", 0),
                      usage.get("completion_tokens", 0), time.monotonic() - started)
        if self.record_to:
            saved = json.loads(self.record_to.read_text()) if self.record_to.exists() else {}
            saved[key_for(messages)] = reply.__dict__
            self.record_to.write_text(json.dumps(saved, indent=1, sort_keys=True))
        return reply


class ReplayModel:
    def __init__(self, path: Path, model: str = "replay"):
        self.model = model
        self.saved = json.loads(Path(path).read_text())

    def complete(self, messages: list[dict]) -> Reply:
        found = self.saved.get(key_for(messages))
        if not found:
            raise ModelError("No recorded reply for this question: run the live evaluation to record it")
        return Reply(**found)
