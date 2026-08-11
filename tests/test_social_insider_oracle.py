"""
tests/test_social_insider_oracle.py — Unit tests for the Social Insider Oracle.

Validates:
  1. SocialMention ingestion and KOL detection
  2. OracleMetrics velocity calculations
  3. Insider Cabal Detection (5-minute window, KOL threshold)
  4. Pre-Volume Sniper evaluation logic
  5. Registry cleanup / TTL pruning
  6. gem_scanner.py integration (oracle import and field population)
"""

import sys
import os
import time
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def fresh_oracle():
    """Return a fresh SocialInsiderOracle instance with default config."""
    from core.social_insider_oracle import SocialInsiderOracle
    return SocialInsiderOracle()


@pytest.fixture
def sample_ca():
    return "0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef"


@pytest.fixture
def mock_gem_candidate(sample_ca):
    """Build a minimal GemCandidate-like object for sniper evaluation."""
    from data.models import Token, GemCandidate
    token = Token(
        address=sample_ca,
        name="Test Gem",
        symbol="TESTGEM",
        chain="base",
        liquidity_usd=200_000.0,
        volume_1h=5_000.0,       # Low — pre-volume condition
        volume_24h=50_000.0,
        price_usd=0.0001,
        market_cap=100_000.0,
    )
    candidate = GemCandidate(token=token)
    candidate.volume_score = 30.0      # Low volume spike score — pre-volume
    candidate.is_safe = True
    return candidate


# ─────────────────────────────────────────────────────────────────────────────
# 1. Module Import Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestOracleImport:
    """Verify the oracle module loads cleanly."""

    def test_module_imports(self):
        """core.social_insider_oracle must import without errors."""
        from core.social_insider_oracle import SocialInsiderOracle, SocialMention, OracleMetrics, get_social_insider_oracle
        oracle = get_social_insider_oracle()
        assert oracle is not None
        assert SocialMention is not None
        assert OracleMetrics is not None
        assert oracle is not None

    def test_oracle_singleton_exists(self):
        """The module-level oracle singleton must be a SocialInsiderOracle instance."""
        from core.social_insider_oracle import get_social_insider_oracle, SocialInsiderOracle
        oracle = get_social_insider_oracle()
        assert isinstance(oracle, SocialInsiderOracle)

    def test_oracle_has_required_methods(self):
        """Oracle must expose all required public methods."""
        from core.social_insider_oracle import SocialInsiderOracle
        inst = SocialInsiderOracle()
        assert callable(getattr(inst, "register_mention", None))
        assert callable(getattr(inst, "check_cabal_pump", None))
        assert callable(getattr(inst, "evaluate_pre_volume_sniper", None))
        assert callable(getattr(inst, "ingest_grok_mentions", None))


# ─────────────────────────────────────────────────────────────────────────────
# 2. SocialMention and KOL Detection
# ─────────────────────────────────────────────────────────────────────────────

class TestSocialMention:
    """Verify mention ingestion and KOL flag assignment."""

    def test_kol_mention_flagged(self, fresh_oracle, sample_ca):
        """A mention from a known KOL handle must be flagged is_kol=True."""
        from core.social_insider_oracle import SocialMention
        mention = SocialMention(
            platform="twitter",
            contract_address=sample_ca,
            sender_id="ansem",     # Known KOL
            sender_name="Ansem",
            text=f"Loading up on {sample_ca} — this is the one",
            followers_count=500_000,
        )
        metrics = fresh_oracle.register_mention(mention, symbol="TESTGEM", chain="base")
        assert mention.is_kol is True, "Known KOL handle should be flagged"
        assert "ansem" in metrics.unique_kols

    def test_non_kol_mention_not_flagged(self, fresh_oracle, sample_ca):
        """A mention from an unknown account must NOT be flagged as KOL."""
        from core.social_insider_oracle import SocialMention
        mention = SocialMention(
            platform="twitter",
            contract_address=sample_ca,
            sender_id="random_retail_user_12345",
            sender_name="Random Retail",
            text=f"wen moon {sample_ca}",
            followers_count=50,
        )
        metrics = fresh_oracle.register_mention(mention, symbol="TESTGEM", chain="base")
        assert mention.is_kol is False, "Unknown account should not be flagged as KOL"
        assert "random_retail_user_12345" not in metrics.unique_kols

    def test_mention_increments_twitter_count(self, fresh_oracle, sample_ca):
        """Twitter mention must increment twitter_count."""
        from core.social_insider_oracle import SocialMention
        mention = SocialMention(
            platform="twitter",
            contract_address=sample_ca,
            sender_id="user1",
            sender_name="User 1",
        )
        metrics = fresh_oracle.register_mention(mention, symbol="TESTGEM", chain="base")
        assert metrics.twitter_count == 1

    def test_mention_increments_telegram_count(self, fresh_oracle, sample_ca):
        """Telegram mention must increment telegram_count."""
        from core.social_insider_oracle import SocialMention
        mention = SocialMention(
            platform="telegram",
            contract_address=sample_ca,
            sender_id="tg_user1",
            sender_name="TG User",
        )
        metrics = fresh_oracle.register_mention(mention, symbol="TESTGEM", chain="base")
        assert metrics.telegram_count == 1

    def test_at_prefix_stripped_from_sender_id(self, fresh_oracle, sample_ca):
        """Sender IDs with @ prefix must be normalized."""
        from core.social_insider_oracle import SocialMention
        mention = SocialMention(
            platform="twitter",
            contract_address=sample_ca,
            sender_id="@ansem",
            sender_name="Ansem",
        )
        fresh_oracle.register_mention(mention, symbol="TESTGEM", chain="base")
        assert mention.sender_id == "ansem", "@ prefix should be stripped"
        assert mention.is_kol is True


# ─────────────────────────────────────────────────────────────────────────────
# 3. Velocity Calculations
# ─────────────────────────────────────────────────────────────────────────────

class TestVelocityCalculations:
    """Verify 5-minute velocity windows."""

    def test_velocity_counts_recent_mentions(self, fresh_oracle, sample_ca):
        """mention_velocity_5m must count only mentions within the last 5 minutes."""
        from core.social_insider_oracle import SocialMention
        now = time.time()
        # 8 recent mentions
        for i in range(8):
            m = SocialMention(
                platform="twitter",
                contract_address=sample_ca,
                sender_id=f"user_{i}",
                sender_name=f"User {i}",
                timestamp=now - 60,  # 1 minute ago
            )
            fresh_oracle.register_mention(m, symbol="TESTGEM", chain="base")
        # 3 old mentions (outside 5-minute window)
        for i in range(3):
            m = SocialMention(
                platform="twitter",
                contract_address=sample_ca,
                sender_id=f"old_user_{i}",
                sender_name=f"Old User {i}",
                timestamp=now - 600,  # 10 minutes ago
            )
            fresh_oracle.register_mention(m, symbol="TESTGEM", chain="base")

        metrics = fresh_oracle.registry[sample_ca.lower()]
        assert metrics.mention_velocity_5m == 8, (
            f"Expected 8 recent mentions, got {metrics.mention_velocity_5m}"
        )

    def test_kol_velocity_5m_counts_only_kols(self, fresh_oracle, sample_ca):
        """kol_velocity_5m must count only KOL mentions in the 5-minute window."""
        from core.social_insider_oracle import SocialMention
        now = time.time()
        kol_handles = ["ansem", "crash", "gcr"]
        for handle in kol_handles:
            m = SocialMention(
                platform="twitter",
                contract_address=sample_ca,
                sender_id=handle,
                sender_name=handle.title(),
                timestamp=now - 30,
            )
            fresh_oracle.register_mention(m, symbol="TESTGEM", chain="base")
        # Add non-KOL mentions
        for i in range(5):
            m = SocialMention(
                platform="twitter",
                contract_address=sample_ca,
                sender_id=f"retail_{i}",
                sender_name=f"Retail {i}",
                timestamp=now - 30,
            )
            fresh_oracle.register_mention(m, symbol="TESTGEM", chain="base")

        metrics = fresh_oracle.registry[sample_ca.lower()]
        assert metrics.kol_velocity_5m == 3, (
            f"Expected 3 KOL mentions, got {metrics.kol_velocity_5m}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 4. Insider Cabal Detection
# ─────────────────────────────────────────────────────────────────────────────

class TestInsiderCabalDetection:
    """Validate coordinated KOL pump detection logic."""

    def test_cabal_detected_with_3_kols(self, fresh_oracle, sample_ca):
        """3 KOLs shilling within 5 minutes must trigger cabal detection."""
        from core.social_insider_oracle import SocialMention
        now = time.time()
        kol_handles = ["ansem", "crash", "gcr"]
        for handle in kol_handles:
            m = SocialMention(
                platform="twitter",
                contract_address=sample_ca,
                sender_id=handle,
                sender_name=handle.title(),
                timestamp=now - 60,
            )
            fresh_oracle.register_mention(m, symbol="TESTGEM", chain="base")

        is_cabal, active_kols = fresh_oracle.check_cabal_pump(sample_ca)
        assert is_cabal is True, "3 KOLs in 5m should trigger cabal detection"
        assert len(active_kols) == 3

    def test_cabal_not_triggered_with_2_kols(self, fresh_oracle, sample_ca):
        """Only 2 KOLs should NOT trigger cabal detection (threshold=3)."""
        from core.social_insider_oracle import SocialMention
        now = time.time()
        for handle in ["ansem", "crash"]:
            m = SocialMention(
                platform="twitter",
                contract_address=sample_ca,
                sender_id=handle,
                sender_name=handle.title(),
                timestamp=now - 60,
            )
            fresh_oracle.register_mention(m, symbol="TESTGEM", chain="base")

        is_cabal, active_kols = fresh_oracle.check_cabal_pump(sample_ca)
        assert is_cabal is False, "Only 2 KOLs should not trigger cabal"

    def test_cabal_not_triggered_for_stale_kol_mentions(self, fresh_oracle, sample_ca):
        """KOL mentions older than 5 minutes must NOT count toward cabal detection."""
        from core.social_insider_oracle import SocialMention
        now = time.time()
        for handle in ["ansem", "crash", "gcr"]:
            m = SocialMention(
                platform="twitter",
                contract_address=sample_ca,
                sender_id=handle,
                sender_name=handle.title(),
                timestamp=now - 400,  # 6+ minutes ago — outside 5m window
            )
            fresh_oracle.register_mention(m, symbol="TESTGEM", chain="base")

        is_cabal, active_kols = fresh_oracle.check_cabal_pump(sample_ca)
        assert is_cabal is False, "Stale KOL mentions should not trigger cabal"

    def test_cabal_returns_empty_for_unknown_ca(self, fresh_oracle):
        """check_cabal_pump on an untracked CA must return (False, [])."""
        is_cabal, active_kols = fresh_oracle.check_cabal_pump("0xunknownaddress")
        assert is_cabal is False
        assert active_kols == []


# ─────────────────────────────────────────────────────────────────────────────
# 5. Pre-Volume Sniper Evaluation
# ─────────────────────────────────────────────────────────────────────────────

class TestPreVolumeSniper:
    """Validate pre-volume sniper bypass logic."""

    def test_sniper_triggered_when_velocity_high_and_volume_low(
        self, fresh_oracle, sample_ca, mock_gem_candidate
    ):
        """High social velocity + low on-chain volume = sniper entry."""
        from core.social_insider_oracle import SocialMention
        now = time.time()
        # Inject 12 mentions in the last 5 minutes (above threshold of 10)
        for i in range(12):
            m = SocialMention(
                platform="twitter",
                contract_address=sample_ca,
                sender_id=f"user_{i}",
                sender_name=f"User {i}",
                timestamp=now - 60,
            )
            fresh_oracle.register_mention(m, symbol="TESTGEM", chain="base")

        should_snipe, reason = fresh_oracle.evaluate_pre_volume_sniper(mock_gem_candidate)
        assert should_snipe is True, f"Should trigger sniper, reason: {reason}"
        assert "velocity" in reason.lower() or "pre-volume" in reason.lower()

    def test_sniper_not_triggered_when_velocity_too_low(
        self, fresh_oracle, sample_ca, mock_gem_candidate
    ):
        """Low social velocity must NOT trigger sniper."""
        from core.social_insider_oracle import SocialMention
        now = time.time()
        # Only 5 mentions — below threshold of 10
        for i in range(5):
            m = SocialMention(
                platform="twitter",
                contract_address=sample_ca,
                sender_id=f"user_{i}",
                sender_name=f"User {i}",
                timestamp=now - 60,
            )
            fresh_oracle.register_mention(m, symbol="TESTGEM", chain="base")

        should_snipe, reason = fresh_oracle.evaluate_pre_volume_sniper(mock_gem_candidate)
        assert should_snipe is False, f"Low velocity should not trigger sniper, reason: {reason}"

    def test_sniper_not_triggered_when_volume_already_spiked(
        self, fresh_oracle, sample_ca, mock_gem_candidate
    ):
        """If on-chain volume has already spiked, sniper bypass must NOT fire."""
        from core.social_insider_oracle import SocialMention
        now = time.time()
        # High social velocity
        for i in range(15):
            m = SocialMention(
                platform="twitter",
                contract_address=sample_ca,
                sender_id=f"user_{i}",
                sender_name=f"User {i}",
                timestamp=now - 30,
            )
            fresh_oracle.register_mention(m, symbol="TESTGEM", chain="base")

        # Simulate volume already spiked
        mock_gem_candidate.volume_score = 90.0
        mock_gem_candidate.token.volume_1h = 150_000.0  # 75% of liquidity — already pumping

        should_snipe, reason = fresh_oracle.evaluate_pre_volume_sniper(mock_gem_candidate)
        assert should_snipe is False, f"Volume already spiked — should not snipe, reason: {reason}"

    def test_sniper_blocked_for_unsafe_token(
        self, fresh_oracle, sample_ca, mock_gem_candidate
    ):
        """Tokens that failed safety checks must never get sniper bypass."""
        from core.social_insider_oracle import SocialMention
        now = time.time()
        for i in range(15):
            m = SocialMention(
                platform="twitter",
                contract_address=sample_ca,
                sender_id=f"user_{i}",
                sender_name=f"User {i}",
                timestamp=now - 30,
            )
            fresh_oracle.register_mention(m, symbol="TESTGEM", chain="base")

        mock_gem_candidate.is_safe = False  # Honeypot / rug flag
        should_snipe, reason = fresh_oracle.evaluate_pre_volume_sniper(mock_gem_candidate)
        assert should_snipe is False, "Unsafe token must never get sniper bypass"
        assert "safety" in reason.lower()

    def test_sniper_returns_false_for_untracked_ca(self, fresh_oracle, mock_gem_candidate):
        """evaluate_pre_volume_sniper on untracked CA must return (False, ...)."""
        should_snipe, reason = fresh_oracle.evaluate_pre_volume_sniper(mock_gem_candidate)
        assert should_snipe is False
        assert "no social oracle" in reason.lower() or "tracking" in reason.lower()


# ─────────────────────────────────────────────────────────────────────────────
# 6. Registry Cleanup
# ─────────────────────────────────────────────────────────────────────────────

class TestRegistryCleanup:
    """Verify TTL-based registry pruning."""

    def test_old_mentions_pruned_on_cleanup(self, fresh_oracle, sample_ca):
        """Mentions older than TTL must be pruned during cleanup."""
        from core.social_insider_oracle import SocialMention
        now = time.time()
        # Add an old mention (older than TTL — 2 hours ago)
        old_mention = SocialMention(
            platform="twitter",
            contract_address=sample_ca,
            sender_id="old_user",
            sender_name="Old User",
            timestamp=now - 7200,  # 2 hours ago
        )
        fresh_oracle.register_mention(old_mention, symbol="TESTGEM", chain="base")
        assert len(fresh_oracle.registry[sample_ca.lower()].mentions) == 1

        # Force cleanup: set last_cleanup far in the past AND backdate first_seen
        fresh_oracle.last_cleanup = now - 700
        fresh_oracle.registry[sample_ca.lower()].first_seen = now - 7200
        fresh_oracle._maybe_cleanup()

        # The token should be removed (no recent mentions and old first_seen)
        assert sample_ca.lower() not in fresh_oracle.registry, (
            "Token with only old mentions should be pruned from registry"
        )

    def test_recent_mentions_survive_cleanup(self, fresh_oracle, sample_ca):
        """Recent mentions must survive the cleanup cycle."""
        from core.social_insider_oracle import SocialMention
        now = time.time()
        recent = SocialMention(
            platform="twitter",
            contract_address=sample_ca,
            sender_id="recent_user",
            sender_name="Recent User",
            timestamp=now - 60,  # 1 minute ago
        )
        fresh_oracle.register_mention(recent, symbol="TESTGEM", chain="base")

        fresh_oracle.last_cleanup = now - 700
        fresh_oracle._maybe_cleanup()

        assert sample_ca.lower() in fresh_oracle.registry, (
            "Token with recent mentions should survive cleanup"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 7. gem_scanner.py Integration
# ─────────────────────────────────────────────────────────────────────────────

class TestGemScannerIntegration:
    """Verify oracle integration points in gem_scanner.py."""

    def test_oracle_import_available_in_scanner(self):
        """gem_scanner.py must expose _SOCIAL_ORACLE_AVAILABLE flag."""
        try:
            import scanner.gem_scanner as gs
            assert hasattr(gs, "_SOCIAL_ORACLE_AVAILABLE"), (
                "_SOCIAL_ORACLE_AVAILABLE flag must be present in gem_scanner module"
            )
        except ImportError as e:
            pytest.skip(f"Full scanner import requires all deps: {e}")

    def test_oracle_flag_is_true(self):
        """_SOCIAL_ORACLE_AVAILABLE must be True when oracle module is present."""
        try:
            import scanner.gem_scanner as gs
            assert gs._SOCIAL_ORACLE_AVAILABLE is True, (
                "Social Oracle module should import successfully"
            )
        except ImportError as e:
            pytest.skip(f"Full scanner import requires all deps: {e}")

    def test_oracle_singleton_accessible_from_scanner(self):
        """_social_oracle singleton must be accessible from gem_scanner module."""
        try:
            import scanner.gem_scanner as gs
            assert gs._social_oracle is not None, (
                "_social_oracle singleton must not be None"
            )
        except ImportError as e:
            pytest.skip(f"Full scanner import requires all deps: {e}")

    def test_gem_candidate_has_oracle_fields(self):
        """GemCandidate model must have all oracle-specific fields."""
        from data.models import GemCandidate, Token
        token = Token(
            address="0x" + "a" * 40,
            name="Test Token",
            symbol="TEST",
            chain="base",
        )
        candidate = GemCandidate(token=token)
        assert hasattr(candidate, "oracle_mention_velocity"), "Missing oracle_mention_velocity"
        assert hasattr(candidate, "oracle_kol_count"), "Missing oracle_kol_count"
        assert hasattr(candidate, "oracle_is_cabal"), "Missing oracle_is_cabal"
        assert hasattr(candidate, "oracle_is_pre_volume"), "Missing oracle_is_pre_volume"
        assert hasattr(candidate, "oracle_sniper_reason"), "Missing oracle_sniper_reason"

    def test_oracle_strategy_tags_in_model(self):
        """GemCandidate strategy_tag must accept oracle-specific values."""
        from data.models import GemCandidate, Token
        token = Token(address="0x" + "b" * 40, name="Cabal Token", symbol="CABAL", chain="solana")
        candidate = GemCandidate(token=token)
        for tag in ["social_oracle_sniper", "insider_cabal_pump", "social_oracle_discovery"]:
            candidate.strategy_tag = tag
            assert candidate.strategy_tag == tag, f"strategy_tag should accept '{tag}'"

    def test_settings_has_oracle_config(self):
        """config/settings.py must expose all oracle configuration variables."""
        from config import settings
        assert hasattr(settings, "ORACLE_VELOCITY_THRESHOLD_5M"), "Missing ORACLE_VELOCITY_THRESHOLD_5M"
        assert hasattr(settings, "ORACLE_CABAL_KOL_THRESHOLD"), "Missing ORACLE_CABAL_KOL_THRESHOLD"
        assert hasattr(settings, "ORACLE_CABAL_WINDOW_S"), "Missing ORACLE_CABAL_WINDOW_S"
        assert hasattr(settings, "KOL_HANDLES_LIST"), "Missing KOL_HANDLES_LIST"
        assert hasattr(settings, "ORACLE_SNIPER_SIZE_MULTIPLIER"), "Missing ORACLE_SNIPER_SIZE_MULTIPLIER"
        # Validate sensible defaults
        assert settings.ORACLE_VELOCITY_THRESHOLD_5M > 0
        assert settings.ORACLE_CABAL_KOL_THRESHOLD >= 2
        assert settings.ORACLE_CABAL_WINDOW_S > 0
        assert 0.0 < settings.ORACLE_SNIPER_SIZE_MULTIPLIER <= 1.0
