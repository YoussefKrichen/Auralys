from __future__ import annotations

import math
import re


def estimate_tokens(text: str | None) -> int:
    if not text:
        return 0
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return 0
    # Heuristic for French/general text: blend character-based and word-based estimates
    # to avoid undercounting very short prompts and overcounting dense punctuation.
    char_estimate = len(normalized) / 4.0
    word_estimate = len(normalized.split()) * 1.35
    return max(1, math.ceil((char_estimate + word_estimate) / 2.0))


def build_token_usage(prompt: str, answer: str, context_text: str | None = None) -> dict[str, int]:
    prompt_tokens = estimate_tokens(prompt)
    answer_tokens = estimate_tokens(answer)
    context_tokens = estimate_tokens(context_text)
    return {
        "prompt_tokens_estimate": prompt_tokens,
        "context_tokens_estimate": context_tokens,
        "answer_tokens_estimate": answer_tokens,
        "total_tokens_estimate": prompt_tokens + answer_tokens,
    }
