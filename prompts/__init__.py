"""Prompt loading for the business AI agent.

Prompt text lives in dedicated template files under this package, not as
Python string literals, so prompt content can be reviewed, diffed, and
edited without touching code.
"""

from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parent


def _load(filename: str) -> str:
    return (_PROMPTS_DIR / filename).read_text(encoding="utf-8").strip()


SYSTEM_PROMPT = _load("system_prompt.md")
