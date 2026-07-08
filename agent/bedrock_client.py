#!/usr/bin/env python3
"""
bedrock_client.py — cached Claude-on-Bedrock caller for the extraction stage.

Reuses the *proven* mechanism from metabolomics_engine/src/llm_rescue.py: the
boto3 **Bedrock Converse API** (`boto3.client("bedrock-runtime").converse(...)`),
the same one already working in Rafi's `py_work` venv with configured AWS creds.
No extra SDK (anthropic[bedrock]) is needed — just boto3, which that venv has.

Two responsibilities:
  1. Call Claude via Bedrock Converse and return parsed JSON.
  2. Cache every response in db/bedrock_cache.db keyed by (model + prompt hash),
     so re-running extraction never re-bills Bedrock for a paper already seen
     (the same discipline as llm_rescue's rescue_cache.db).

boto3 is imported lazily inside the call, so this module imports fine without it
(the mock extractor and the eval-harness plumbing run without touching Bedrock).

Run with the metaflow venv that already has boto3 + AWS configured, e.g.:
    py_work agent/eval_extract.py --real
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CACHE_PATH = os.path.join(ROOT, "db", "bedrock_cache.db")

# Default to the Bedrock inference profile already enabled in Rafi's account
# (same as llm_rescue.py). Override with LEAF_BEDROCK_MODEL. Opus is available as
# us.anthropic.claude-opus-4-8 once that profile is enabled in Bedrock.
DEFAULT_MODEL = os.environ.get("LEAF_BEDROCK_MODEL", "us.anthropic.claude-sonnet-4-6")
DEFAULT_REGION = os.environ.get("AWS_REGION", "us-east-1")

_bedrock = None  # module-level boto3 client, created once (mirrors llm_rescue)


def _get_bedrock(region: str):
    global _bedrock
    if _bedrock is None:
        try:
            import boto3  # lazy — mock/eval plumbing doesn't need it
            from botocore.config import Config
        except ImportError as e:  # noqa: BLE001
            raise RuntimeError(
                "boto3 not installed. Run the leaf agent with the metaflow venv "
                "(py_work), which already has boto3 + AWS configured, or `pip install boto3`."
            ) from e
        # full-paper extraction generates for longer than botocore's default 60s
        # read timeout; give it room and bound retries so a slow call isn't re-billed.
        cfg = Config(read_timeout=300, connect_timeout=15,
                     retries={"max_attempts": 2, "mode": "standard"})
        _bedrock = boto3.client("bedrock-runtime", region_name=region, config=cfg)
    return _bedrock


def _cache_conn():
    conn = sqlite3.connect(CACHE_PATH)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS bedrock_cache (
               cache_key TEXT PRIMARY KEY, model TEXT, response TEXT, created_at TEXT
           )"""
    )
    return conn


def _key(model: str, system: str, user: str) -> str:
    h = hashlib.sha256()
    for part in (model, system, user):
        h.update(part.encode())
        h.update(b"\x00")
    return h.hexdigest()


def _parse_json(text: str) -> dict:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        s, e = text.find("{"), text.rfind("}")
        if s != -1 and e > s:
            return json.loads(text[s:e + 1])
        raise


class BedrockClient:
    def __init__(self, model: str = DEFAULT_MODEL, region: str = DEFAULT_REGION,
                 max_tokens: int = 16000):
        self.model = model
        self.region = region
        self.max_tokens = max_tokens

    def complete_json(self, system: str, user: str, schema: dict) -> dict:
        """Return Claude's JSON output via Bedrock Converse, cached by prompt hash."""
        ck = _key(self.model, system, user)
        conn = _cache_conn()
        row = conn.execute(
            "SELECT response FROM bedrock_cache WHERE cache_key = ?", (ck,)
        ).fetchone()
        if row is not None:
            conn.close()
            return {"cache_key": ck, "cached": True, **json.loads(row[0])}

        client = _get_bedrock(self.region)
        # Converse has no output_config.format; instruct JSON in-prompt and parse
        # (extract.py's schema is included so the model targets the exact shape).
        user_json = (
            user + "\n\nReturn ONLY a JSON object matching this schema, no prose:\n"
            + json.dumps(schema)
        )
        resp = client.converse(
            modelId=self.model,
            system=[{"text": system}],
            messages=[{"role": "user", "content": [{"text": user_json}]}],
            inferenceConfig={"maxTokens": self.max_tokens, "temperature": 0.0},
        )
        raw = resp["output"]["message"]["content"][0]["text"].strip()
        if resp.get("stopReason") == "max_tokens":
            # truncated JSON → surface rather than silently mis-parse (llm_rescue GAP-006)
            raise RuntimeError(
                f"Bedrock response hit maxTokens={self.max_tokens} (truncated). "
                f"Raise max_tokens or split the paper. Tail: …{raw[-80:]!r}"
            )
        parsed = _parse_json(raw)
        conn.execute(
            "INSERT OR REPLACE INTO bedrock_cache VALUES (?,?,?,?)",
            (ck, self.model, json.dumps(parsed, ensure_ascii=False),
             time.strftime("%Y-%m-%dT%H:%M:%S")),
        )
        conn.commit()
        conn.close()
        return {"cache_key": ck, "cached": False, **parsed}
