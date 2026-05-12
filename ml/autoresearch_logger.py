"""
ml/autoresearch_logger.py — Autoresearch Weight Logger

Uses Grok to analyze changes in ML-optimized weights and generate a plain-English
"Trade Journal" entry explaining WHY the weights likely changed based on recent
market conditions.

Fixed: Uses shared grok_client.py with correct Responses API format, global rate
limiting, and prompt caching via prompt_cache_key.
"""
import json
import logging
import os
from datetime import datetime
from typing import Optional
from data.providers.grok_client import call_grok

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# System Prompt — kept static for optimal prompt caching
# xAI caches identical system prompt prefixes server-side. Do NOT embed
# dynamic content here — all variable data goes in the user message.
# ─────────────────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are the Autoresearch Analyst for a crypto trading bot.
Your job is to look at how the machine learning model has adjusted the scoring weights
and explain WHY these changes happened in plain English.

You will be given:
1. The OLD weights
2. The NEW weights
3. The current macro regime

Return ONLY valid JSON with these exact fields:
{
  "biggest_increase": "<feature name>",
  "biggest_decrease": "<feature name>",
  "explanation": "<A 2-3 sentence plain English explanation of what the bot learned and why it adapted this way>"
}"""


def log_weight_changes(old_weights: dict, new_weights: dict, macro_regime: str) -> Optional[dict]:
    """
    Generate an autoresearch explanation for weight changes using Grok.

    Returns a dict with biggest_increase, biggest_decrease, explanation.
    Returns None if API key missing or request fails.
    """
    # All dynamic data goes in the user message (system prompt stays static for caching)
    context = f"""Macro Regime: {macro_regime}

OLD Weights:
{json.dumps(old_weights, indent=2)}

NEW Weights:
{json.dumps(new_weights, indent=2)}

Analyze the changes and explain what the bot learned."""

    logger.info("Autoresearch Logger: Analyzing weight changes...")

    result = call_grok(
        system_prompt=SYSTEM_PROMPT,
        user_message=context,
        cache_key="autoresearch",
        temperature=0.4,
        max_output_tokens=500,
        parse_json=True,
        timeout=15,
        module="autoresearch",
    )

    if result is None:
        logger.debug("Autoresearch Logger: No result from Grok")
        return None

    # Save to a local journal file
    journal_path = "output/autoresearch_journal.json"
    journal_entry = {
        "timestamp": datetime.now().isoformat(),
        "macro_regime": macro_regime,
        "biggest_increase": result.get("biggest_increase"),
        "biggest_decrease": result.get("biggest_decrease"),
        "explanation": result.get("explanation"),
    }

    journal = []
    if os.path.exists(journal_path):
        try:
            with open(journal_path, "r") as f:
                journal = json.load(f)
        except Exception:
            pass

    journal.append(journal_entry)

    # Keep last 50 entries
    journal = journal[-50:]

    os.makedirs(os.path.dirname(journal_path), exist_ok=True)
    with open(journal_path, "w") as f:
        json.dump(journal, f, indent=2)

    logger.info(f"Autoresearch Logger: {result.get('explanation')}")
    return result
