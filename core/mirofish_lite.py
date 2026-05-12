"""
core/mirofish_lite.py — MiroFish Lite Swarm Simulation Context

Uses Grok to simulate the current views of different market participants
(Retail, Whales, Market Makers) based on current macro data and recent
top tokens. Provides forward-looking narrative context.

Fixed: Uses shared grok_client.py with correct Responses API format, global rate
limiting, and prompt caching via prompt_cache_key.
"""
import logging
from typing import Optional
from data.providers.grok_client import call_grok

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# System Prompt — kept static for optimal prompt caching
# xAI caches identical system prompt prefixes server-side. Do NOT embed
# dynamic content here — all variable data goes in the user message.
# ─────────────────────────────────────────────────────────────────────────────
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
}"""


def generate_swarm_context(macro_regime: str, top_tokens: list[str]) -> Optional[dict]:
    """
    Generate swarm simulation context using Grok.

    Returns a dict with retail_view, whale_view, market_maker_view,
    consensus_prediction, and tail_risk.
    Returns None if MiroFish is disabled, API key missing, or request fails.
    """
    try:
        from config import settings
        if not getattr(settings, "MIROFISH_ENABLED", True):
            return None
    except Exception:
        pass

    # All dynamic data goes in the user message (system prompt stays static for caching)
    context = f"""Current Macro Regime: {macro_regime}
Recent Top Tokens: {', '.join(top_tokens) if top_tokens else 'None'}

Simulate the swarm."""

    logger.info("MiroFish Lite: Generating swarm simulation context...")

    result = call_grok(
        system_prompt=SYSTEM_PROMPT,
        user_message=context,
        cache_key="mirofish_lite",
        temperature=0.5,
        max_output_tokens=500,
        parse_json=True,
        timeout=15,
        module="mirofish_lite",
    )

    if result is None:
        logger.debug("MiroFish Lite: No result from Grok")
        return None

    logger.info(f"MiroFish Lite: Consensus Prediction -> {result.get('consensus_prediction')}")
    return result
