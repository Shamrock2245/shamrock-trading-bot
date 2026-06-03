import reflex as rx
import json
import asyncio
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
    
    positions: dict = {}
    daily_goal: dict = {}
    blue_chip: dict = {}
    scanner_gems: list = []
    bot_mode: str = "paper"
    last_updated: float = 0
    
    # State flags
    is_live: bool = False
    
    def check_auth(self, password: str):
        # Very simple authentication for the dashboard
        # Using a hardcoded Fortune 50 grade password check, or from env
        correct_password = os.environ.get("DASHBOARD_PASSWORD", "shamrock2026")
        if password == correct_password:
            self.is_authenticated = True
            self.auth_error = ""
        else:
            self.auth_error = "Invalid password. Access denied."
            
    def logout(self):
        self.is_authenticated = False
        
    def load_data(self):
        """Load JSON files from the bot's output."""
        if self.is_authenticated:
            self._read_data()
            
    def _read_data(self):
        """Read data from the bot's output directories."""
        # Positions
        pos_file = OUTPUT_DIR / "positions.json"
        if pos_file.exists():
            try:
                with open(pos_file, "r") as f:
                    self.positions = json.load(f)
            except Exception:
                pass
                
        # Daily Goal
        goal_file = OUTPUT_DIR / "daily_goal_state.json"
        if goal_file.exists():
            try:
                with open(goal_file, "r") as f:
                    self.daily_goal = json.load(f)
            except Exception:
                pass
                
        # Blue Chip
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
        
    def go_live(self, confirmation: str):
        """Trigger the Go Live sequence."""
        if confirmation == "CONFIRM_LIVE":
            DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)
            override_file = DASHBOARD_DIR / "live_mode_override.json"
            with open(override_file, "w") as f:
                json.dump({"mode": "live", "timestamp": time.time()}, f)
            self.is_live = True
            self.bot_mode = "live"
            
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
