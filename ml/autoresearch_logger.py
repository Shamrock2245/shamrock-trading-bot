"""
ml/autoresearch_logger.py — Autoresearch Weight Logger
Uses Grok to analyze changes in ML-optimized weights and generate a plain-English
"Trade Journal" entry explaining WHY the weights likely changed based on recent market conditions.
"""
import json
import logging
import os
from datetime import datetime
from typing import Optional
from data.http_session import get_session

logger = logging.getLogger(__name__)

GROK_RESPONSES_URL = "https://api.x.ai/v1/responses"
GROK_MODEL = "grok-4-1-fast-non-reasoning"

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
}
"""

def _get_api_key() -> str:
    try:
        from config import settings
        key = getattr(settings, "GROK_API_KEY", "")
        if key:
            return key
    except ImportError:
        pass
    return os.getenv("GROK_API_KEY", "")

def log_weight_changes(old_weights: dict, new_weights: dict, macro_regime: str) -> Optional[dict]:
    """
    Generate an autoresearch explanation for weight changes using Grok.
    """
    api_key = _get_api_key()
    if not api_key:
        logger.warning("Autoresearch Logger: GROK_API_KEY not found. Skipping explanation.")
        return None

    session = get_session()
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    context = f"""
Macro Regime: {macro_regime}

OLD Weights:
{json.dumps(old_weights, indent=2)}

NEW Weights:
{json.dumps(new_weights, indent=2)}

Analyze the changes and explain what the bot learned.
"""

    payload = {
        "model": GROK_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": context}
        ],
        "temperature": 0.4,
        "response_format": {"type": "json_object"}
    }

    try:
        logger.info("Autoresearch Logger: Analyzing weight changes...")
        resp = session.post(GROK_RESPONSES_URL, headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        
        content = data["choices"][0]["message"]["content"]
        result = json.loads(content)
        
        # Save to a local journal file
        journal_path = "output/autoresearch_journal.json"
        journal_entry = {
            "timestamp": datetime.now().isoformat(),
            "macro_regime": macro_regime,
            "biggest_increase": result.get("biggest_increase"),
            "biggest_decrease": result.get("biggest_decrease"),
            "explanation": result.get("explanation")
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
        
    except Exception as e:
        logger.error(f"Autoresearch Logger: Failed to analyze weights: {e}")
        return None
