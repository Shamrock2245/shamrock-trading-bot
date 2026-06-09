import os
import sys
import unittest
from unittest.mock import MagicMock, patch

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Minimal stubs
solders_stub = MagicMock()
solana_stub = MagicMock()
base58_stub = MagicMock()

http_session_stub = MagicMock()
mock_response = MagicMock()
mock_response.status_code = 200
mock_response.json.return_value = {
    "outAmount": "1000000",
    "priceImpactPct": "1.5",
    "swapTransaction": "base64_tx_data"
}
http_session_stub.get_session.return_value.get.return_value = mock_response
http_session_stub.get_session.return_value.post.return_value = mock_response

mev_stub = MagicMock()
jito_result_mock = MagicMock()
jito_result_mock.success = True
jito_result_mock.bundle_id = "jito_test_bundle"
mev_stub.execute_solana_via_jito.return_value = jito_result_mock

_STUBS = {
    "solders": solders_stub,
    "solders.keypair": MagicMock(),
    "solders.transaction": MagicMock(),
    "solana": solana_stub,
    "base58": base58_stub,
    "data.http_session": http_session_stub,
    "core.mev_protection": mev_stub,
}

class TestExecuteSellSolana(unittest.TestCase):
    def test_paper_mode_returns_paper_tx(self):
        with patch.dict(sys.modules, _STUBS):
            from core.sell_engine import execute_sell_solana
            result = execute_sell_solana(
                token_mint="TokenMint123",
                token_amount_units=1000,
                wallet_public_key="PubKey",
                wallet_private_key_env="DUMMY_KEY",
                is_paper=True
            )
            self.assertTrue(result.success)
            self.assertEqual(result.tx_hash, "PAPER_TX")
            self.assertEqual(result.execution_path, "paper")

    @patch.dict(os.environ, {"DUMMY_KEY": "dummy_private_key"})
    def test_live_mode_calls_jito(self):
        with patch.dict(sys.modules, _STUBS):
            from core.sell_engine import execute_sell_solana
            result = execute_sell_solana(
                token_mint="TokenMint123",
                token_amount_units=1000,
                wallet_public_key="PubKey",
                wallet_private_key_env="DUMMY_KEY",
                is_paper=False
            )
            self.assertTrue(result.success)
            self.assertEqual(result.tx_hash, "jito_test_bundle")
            self.assertEqual(result.execution_path, "jito")

if __name__ == "__main__":
    unittest.main()
