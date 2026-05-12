"""
core/mirofish_lite.py — MiroFish Lite Swarm Simulation Context
Uses Grok to simulate the current views of different market participants (Retail, Whales, Market Makers)
based on current macro data and recent top tokens. Provides forward-looking narrative context.
"""
import json
import logging
import os
import time
from typing import Optional
from data.http_session import get_session

logger = logging.getLogger(__name__)

GROK_RESPONSES_URL = "https://api.x.ai/v1/responses"
GROK_MODEL = "grok-4-1-fast-non-reasoning"

SYSTEM_PROMPT = """You are the MiroFish Swarm Simulator for a crypto trading bot.
Your job is to simulate the current views and likely next actions of different market participants
based on the provided macro regime and recent top tokens.

Simulate these 3 actors:
1. Retail Trader (FOMO, social sentiment, momentum)
2. Whale / Smart Money (Accumulation, liquidity, mean reversion)
3. Market Maker (Volatility, hedging, fee harvesting)

Return ONLY valid JSON with these exact fields:
{
  "retail_view": "<what retail is thinking/doing>",
  "whale_view": "<what whales are thinking/doing>",
  "market_maker_view": "<what MMs are thinking/doing>",
  "consensus_prediction": "<what is the most likely short-term market direction>",
  "tail_risk": "<what is the biggest hidden risk right now>"
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

def generate_swarm_context(macro_regime: str, top_tokens: list[str]) -> Optional[dict]:
    try:
        from config import settings
        if not getattr(settings, "MIROFISH_ENABLED", True):
            return None
    except Exception:
        pass
    """
    Generate swarm simulation context using Grok.
    """
    api_key = _get_api_key()
    if not api_key:
        logger.warning("MiroFish Lite: GROK_API_KEY not found. Skipping simulation.")
        return None

    session = get_session()
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    context = f"""
Current Macro Regime: {macro_regime}
Recent Top Tokens: {', '.join(top_tokens) if top_tokens else 'None'}

Simulate the swarm.
"""

    payload = {
        "model": GROK_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": context}
        ],
        "temperature": 0.5,
        "response_format": {"type": "json_object"}
    }

    try:
        logger.info("MiroFish Lite: Generating swarm simulation context...")
        resp = session.post(GROK_RESPONSES_URL, headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        
        content = data["choices"][0]["message"]["content"]
        result = json.loads(content)
        
        logger.info(f"MiroFish Lite: Consensus Prediction -> {result.get('consensus_prediction')}")
        return result
        
    except Exception as e:
        logger.error(f"MiroFish Lite: Failed to generate context: {e}")
        return None
