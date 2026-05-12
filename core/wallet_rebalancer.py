import asyncio
from typing import Dict, List
from datetime import datetime, timedelta
import logging

from core.regime_filter import get_current_regime
from risk.rl_sizer import get_rl_confidence
from utils.moralis_stream import get_wallet_balance, get_last_trade_time
from config import config

logger = logging.getLogger(__name__)

class StaleWalletRebalancer:
    def __init__(self):
        self.last_rebalance = {}

    async def check_and_rebalance(self, wallets: List[Dict]):
        regime = get_current_regime()
        if regime == 'CHOP':
            return  # Ghost in chop

        nuclear_target = 0.75 if regime == 'EXPANSION' else 0.55

        for wallet in wallets:
            if self.is_stale(wallet):
                amount = self.calculate_rebalance_amount(wallet, nuclear_target)
                if amount > 250:  # Min move
                    await self.execute_rebalance(wallet, amount)

    def is_stale(self, wallet: Dict) -> bool:
        last_trade = get_last_trade_time(wallet['address'])
        if last_trade and (datetime.now() - last_trade) < timedelta(hours=12):
            return False
        balance = get_wallet_balance(wallet['address'])
        if balance.get('USDC', 0) / balance.get('total', 1) > 0.7:
            return True
        return False

    def calculate_rebalance_amount(self, wallet, nuclear_target):
        # Dynamic calc
        return wallet['usdc_balance'] * 0.6  # Example

    async def execute_rebalance(self, wallet, amount):
        # Use existing Jupiter/1inch routing
        logger.info(f'Rebalancing ${amount} from {wallet["address"]} to Nuclear')
        # Implement transfer logic here
        self.last_rebalance[wallet['address']] = datetime.now()

rebalancer = StaleWalletRebalancer()