import reflex as rx
import json
from pathlib import Path
import os
import time

# Paths to the bot's data
PROJECT_ROOT = Path(__file__).parent.parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
DASHBOARD_DIR = PROJECT_ROOT / "data" / "dashboard"
REQUESTS_DIR = DASHBOARD_DIR / "requests"


class AppState(rx.State):
    """The app state."""
    is_authenticated: bool = False
    auth_error: str = ""
    password: str = ""

    def set_password(self, text: str):
        self.password = text

    # Raw data loaded from JSON files
    positions_list: list = []       # list of position dicts from positions.json
    daily_goal: dict = {}           # daily_goal_state.json
    blue_chip: dict = {}            # blue_chip_tracker.json
    scanner_gems: list = []         # scanner_gems.json
    bot_status: dict = {}           # data/dashboard/bot_status.json

    bot_mode: str = "paper"
    last_updated: float = 0

    # State flags
    is_live: bool = False

    # ── Computed display vars (avoids f-string + state var bugs) ──────────────
    @rx.var
    def total_pnl_display(self) -> str:
        """Today's realized P&L formatted for display."""
        val = self.daily_goal.get("today_profit_usd", 0.0)
        try:
            fval = float(val)
            sign = "+" if fval >= 0 else ""
            return f"{sign}${fval:,.2f}"
        except (TypeError, ValueError):
            return "$0.00"

    @rx.var
    def win_rate_display(self) -> str:
        """Win rate from daily history."""
        history = self.daily_goal.get("daily_history", [])
        if not history:
            return "0%"
        try:
            hits = sum(1 for d in history if d.get("hit", False))
            rate = hits / len(history) * 100
            return f"{rate:.0f}%"
        except Exception:
            return "0%"

    @rx.var
    def open_positions_count(self) -> int:
        """Number of open positions."""
        try:
            return len([p for p in self.positions_list if p.get("status") == "open"])
        except Exception:
            return 0

    @rx.var
    def open_positions_count_display(self) -> str:
        return str(self.open_positions_count)

    @rx.var
    def scanner_gems_count_display(self) -> str:
        return str(len(self.scanner_gems))

    @rx.var
    def bot_cycle_display(self) -> str:
        cycle = self.bot_status.get("cycle", 0)
        return f"Cycle #{cycle}"

    @rx.var
    def bot_uptime_display(self) -> str:
        secs = self.bot_status.get("uptime_seconds", 0)
        try:
            secs = int(secs)
            h = secs // 3600
            m = (secs % 3600) // 60
            return f"{h}h {m}m"
        except Exception:
            return "—"

    @rx.var
    def daily_target_display(self) -> str:
        val = self.daily_goal.get("current_target_usd", 500.0)
        try:
            return f"${float(val):,.0f}"
        except Exception:
            return "$500"

    @rx.var
    def daily_progress_pct(self) -> float:
        profit = float(self.daily_goal.get("today_profit_usd", 0.0) or 0.0)
        target = float(self.daily_goal.get("current_target_usd", 500.0) or 500.0)
        if target <= 0:
            return 0.0
        return min(round(profit / target * 100, 1), 100.0)

    @rx.var
    def daily_progress_display(self) -> str:
        return f"{self.daily_progress_pct:.1f}%"

    @rx.var
    def open_positions(self) -> list:
        """Open positions only."""
        try:
            return [p for p in self.positions_list if p.get("status") == "open"]
        except Exception:
            return []

    @rx.var
    def last_updated_display(self) -> str:
        if self.last_updated == 0:
            return "Never"
        try:
            import datetime
            dt = datetime.datetime.fromtimestamp(self.last_updated)
            return dt.strftime("%H:%M:%S")
        except Exception:
            return "—"

    @rx.var
    def bot_is_running(self) -> bool:
        return bool(self.bot_status.get("is_running", False))

    @rx.var
    def bot_status_display(self) -> str:
        if self.bot_is_running:
            return "RUNNING"
        return "OFFLINE"

    # ── Auth ──────────────────────────────────────────────────────────────────
    def check_auth(self, password: str):
        correct_password = os.environ.get("DASHBOARD_PASSWORD", "shamrock2026")
        if password == correct_password:
            self.is_authenticated = True
            self.auth_error = ""
        else:
            self.auth_error = "Invalid password. Access denied."

    def logout(self):
        self.is_authenticated = False

    # ── Data Loading ──────────────────────────────────────────────────────────
    def load_data(self):
        """Load JSON files from the bot's output. Called on page load."""
        if self.is_authenticated:
            self._read_data()

    def _read_data(self):
        """Read data from the bot's output directories."""
        # Positions (list of position dicts)
        pos_file = OUTPUT_DIR / "positions.json"
        if pos_file.exists():
            try:
                with open(pos_file, "r") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self.positions_list = data
                    elif isinstance(data, dict):
                        # Legacy format: flatten to list
                        self.positions_list = list(data.values()) if data else []
                    else:
                        self.positions_list = []
            except Exception:
                pass

        # Daily Goal state
        goal_file = OUTPUT_DIR / "daily_goal_state.json"
        if goal_file.exists():
            try:
                with open(goal_file, "r") as f:
                    self.daily_goal = json.load(f)
            except Exception:
                pass

        # Blue Chip tracker
        bc_file = OUTPUT_DIR / "blue_chip_tracker.json"
        if bc_file.exists():
            try:
                with open(bc_file, "r") as f:
                    self.blue_chip = json.load(f)
            except Exception:
                pass

        # Scanner Gems
        scanner_file = OUTPUT_DIR / "scanner_gems.json"
        if scanner_file.exists():
            try:
                with open(scanner_file, "r") as f:
                    self.scanner_gems = json.load(f)
            except Exception:
                pass

        # Bot status (from data/dashboard/bot_status.json)
        status_file = DASHBOARD_DIR / "bot_status.json"
        if status_file.exists():
            try:
                with open(status_file, "r") as f:
                    self.bot_status = json.load(f)
            except Exception:
                pass

        # Bot mode override
        override_file = DASHBOARD_DIR / "live_mode_override.json"
        if override_file.exists():
            try:
                with open(override_file, "r") as f:
                    data = json.load(f)
                    if data.get("mode") == "live":
                        self.is_live = True
                        self.bot_mode = "live"
                    else:
                        self.is_live = False
                        self.bot_mode = "paper"
            except Exception:
                pass

        self.last_updated = time.time()

    # ── Actions ───────────────────────────────────────────────────────────────
    def go_live(self, confirmation: str):
        """Trigger the Go Live sequence."""
        if confirmation == "CONFIRM_LIVE":
            DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)
            override_file = DASHBOARD_DIR / "live_mode_override.json"
            with open(override_file, "w") as f:
                json.dump({"mode": "live", "timestamp": time.time()}, f)
            self.is_live = True
            self.bot_mode = "live"

    def go_paper(self):
        """Switch back to paper mode."""
        DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)
        override_file = DASHBOARD_DIR / "live_mode_override.json"
        with open(override_file, "w") as f:
            json.dump({"mode": "paper", "timestamp": time.time()}, f)
        self.is_live = False
        self.bot_mode = "paper"

    def force_scan(self):
        """Force a Moralis scan."""
        REQUESTS_DIR.mkdir(parents=True, exist_ok=True)
        request_file = REQUESTS_DIR / f"force_scan_{int(time.time())}.json"
        with open(request_file, "w") as f:
            json.dump({"action": "force_scan", "timestamp": time.time()}, f)

    def manual_sell(self, token_address: str, current_price: float):
        """Trigger a manual sell."""
        REQUESTS_DIR.mkdir(parents=True, exist_ok=True)
        request_file = REQUESTS_DIR / f"manual_sell_{token_address}_{int(time.time())}.json"
        with open(request_file, "w") as f:
            json.dump({
                "action": "manual_sell",
                "token_address": token_address,
                "current_price": current_price,
                "timestamp": time.time()
            }, f)
