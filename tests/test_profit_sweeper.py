import pytest
from unittest.mock import patch, MagicMock
from core.profit_sweeper import execute_sweep

@pytest.fixture
def mock_env(monkeypatch):
    monkeypatch.setenv("MODE", "live")
    monkeypatch.setenv("WALLET_ADDRESS_C", "0x1234567890123456789012345678901234567890")
    monkeypatch.setenv("WALLET_PRIVATE_KEY_PRIMARY", "dummy_key")

@patch("core.profit_sweeper.Web3")
@patch("core.profit_sweeper.get_usdc_balance")
def test_execute_sweep_success(mock_get_usdc_balance, mock_web3_class, mock_env):
    # Mocking balance to trigger sweep
    mock_get_usdc_balance.return_value = 5000.0  # Above 2000 + 50 buffer
    
    # Mock Web3 instance
    mock_w3 = MagicMock()
    mock_w3.is_connected.return_value = True
    mock_w3.eth.get_transaction_count.return_value = 1
    mock_w3.eth.gas_price = 1000000000
    # Mock receipt confirmation (status=1 means success)
    mock_receipt = MagicMock()
    mock_receipt.status = 1
    mock_w3.eth.wait_for_transaction_receipt.return_value = mock_receipt
    mock_web3_class.return_value = mock_w3
    mock_web3_class.is_address.return_value = True
    
    # Mock contract transfer
    mock_contract = MagicMock()
    mock_w3.eth.contract.return_value = mock_contract
    
    result = execute_sweep()
    assert result is True
    assert mock_contract.functions.transfer.called

@patch("core.profit_sweeper.Web3")
@patch("core.profit_sweeper.get_usdc_balance")
def test_execute_sweep_cooldown(mock_get_usdc_balance, mock_web3_class, mock_env):
    mock_get_usdc_balance.return_value = 5000.0
    mock_web3_class.is_address.return_value = True
    
    # First execution should succeed
    execute_sweep()
    
    # Second execution should fail due to cooldown
    result = execute_sweep()
    assert result is False

@patch("core.profit_sweeper.get_usdc_balance")
def test_execute_sweep_not_live_mode(mock_get_usdc_balance, monkeypatch):
    monkeypatch.setenv("MODE", "paper")
    monkeypatch.setenv("WALLET_ADDRESS_C", "0x1234567890123456789012345678901234567890")
    
    result = execute_sweep()
    assert result is False
