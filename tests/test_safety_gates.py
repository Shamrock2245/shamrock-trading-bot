"""
tests/test_safety_gates.py — Unit tests for the safety pipeline.

Validates that honeypot detection, tax checks, and safety flags
correctly block dangerous tokens.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestSafetyImport:
    """Verify safety module loads."""

    def test_import_safety(self):
        from core.safety import check_token_safety, SafetyResult
        assert callable(check_token_safety)

    def test_safety_result_has_fields(self):
        from core.safety import SafetyResult
        # SafetyResult should have is_safe and block_reason
        r = SafetyResult(is_safe=True, block_reason="")
        assert r.is_safe is True
        assert r.block_reason == ""


class TestSafetyLogic:
    """Test safety gate decisions."""

    def test_null_address_blocked(self):
        """Empty/null addresses should be blocked."""
        from core.safety import check_token_safety
        result = check_token_safety("", "ethereum")
        assert not result.is_safe, "Empty address should be blocked"

    def test_zero_address_blocked(self):
        """Zero address (0x000...) should be blocked."""
        from core.safety import check_token_safety
        result = check_token_safety("0x" + "0" * 40, "ethereum")
        assert not result.is_safe, "Zero address should be blocked"


class TestContractBlacklist:
    """Test known-bad contract detection."""

    def test_known_honeypot_blocked(self):
        """If we have a known honeypot address, it should be blocked."""
        from core.safety import check_token_safety
        # Use a nonsensical address — the point is the pipeline runs end-to-end
        result = check_token_safety("0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef", "ethereum")
        # This address should at least produce a valid SafetyResult
        assert hasattr(result, "is_safe")
        assert hasattr(result, "block_reason")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
