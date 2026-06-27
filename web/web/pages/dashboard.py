"""Command Center dashboard page."""
import reflex as rx
from web.state import AppState
from web.pages.layout import dashboard_layout


def stat_card(title: str, value: rx.Component, icon: str, color: str) -> rx.Component:
    return rx.card(
        rx.hstack(
            rx.box(
                rx.icon(icon, size=24, color=f"var(--{color}-9)"),
                padding="12px",
                background=f"var(--{color}-3)",
                border_radius="12px",
            ),
            rx.vstack(
                rx.text(title, size="2", color="gray"),
                value,
                spacing="1",
            ),
            align_items="center",
            spacing="4",
        ),
        size="2",
        width="100%",
    )


def progress_bar(pct: rx.Var) -> rx.Component:
    """Daily goal progress bar."""
    return rx.progress(value=pct, color_scheme="green")


def ledger_row(item: dict) -> rx.Component:
    return rx.table.row(
        rx.table.cell(rx.text(item["date"], weight="bold")),
        rx.table.cell(rx.badge(item["trades"] + " Trades", color_scheme="gray", variant="soft")),
        rx.table.cell(rx.text(item["profit"], weight="bold", color=item["profit_color"])),
    )


@rx.page(route="/", title="Command Center", on_load=AppState.load_data)
def index() -> rx.Component:
    return dashboard_layout(
        rx.vstack(
            # ── Header ────────────────────────────────────────────────────────
            rx.hstack(
                rx.vstack(
                    rx.heading("Command Center", size="8", weight="bold"),
                    rx.hstack(
                        rx.icon("clock", size=14, color="gray"),
                        rx.text(
                            "Last updated: ",
                            AppState.last_updated_display,
                            size="2",
                            color="gray",
                        ),
                        spacing="1",
                        align_items="center",
                    ),
                    spacing="1",
                ),
                rx.spacer(),
                rx.hstack(
                    rx.button(
                        rx.icon("refresh-cw", size=16),
                        "Refresh",
                        on_click=AppState.load_data,
                        color_scheme="gray",
                        variant="soft",
                        size="3",
                    ),
                    rx.button(
                        rx.icon("zap", size=16),
                        "Force Scan",
                        on_click=AppState.force_scan,
                        color_scheme="blue",
                        variant="soft",
                        size="3",
                    ),
                    spacing="2",
                ),
                width="100%",
                align_items="center",
            ),
            rx.divider(margin_y="1em", opacity="0.2"),

            # ── Key Stats Row ─────────────────────────────────────────────────
            rx.grid(
                stat_card(
                    "Realized P&L",
                    rx.text(AppState.realized_pnl_display, size="5", weight="bold"),
                    "dollar-sign",
                    "green",
                ),
                stat_card(
                    "Unrealized P&L",
                    rx.text(AppState.unrealized_pnl_display, size="5", weight="bold"),
                    "activity",
                    "blue",
                ),
                stat_card(
                    "Open Positions",
                    rx.text(AppState.open_positions_count_display, size="5", weight="bold"),
                    "briefcase",
                    "purple",
                ),
                stat_card(
                    "Scanner Gems",
                    rx.text(AppState.scanner_gems_count_display, size="5", weight="bold"),
                    "radar",
                    "orange",
                ),
                columns="4",
                spacing="4",
                width="100%",
            ),

            # ── Bot Status Row ────────────────────────────────────────────────
            rx.grid(
                stat_card(
                    "Bot Status",
                    rx.badge(
                        AppState.bot_status_display,
                        color_scheme=rx.cond(AppState.bot_is_running, "green", "red"),
                        variant="solid",
                        size="2",
                    ),
                    "activity",
                    "green",
                ),
                stat_card(
                    "Scan Cycle",
                    rx.text(AppState.bot_cycle_display, size="5", weight="bold"),
                    "rotate-cw",
                    "cyan",
                ),
                stat_card(
                    "Uptime",
                    rx.text(AppState.bot_uptime_display, size="5", weight="bold"),
                    "timer",
                    "teal",
                ),
                stat_card(
                    "Daily Target",
                    rx.text(AppState.daily_target_display, size="5", weight="bold"),
                    "target",
                    "yellow",
                ),
                columns="4",
                spacing="4",
                width="100%",
            ),

            rx.box(margin_top="1em"),

            # ── Daily Goal Progress ───────────────────────────────────────────
            rx.card(
                rx.vstack(
                    rx.hstack(
                        rx.heading("Daily Goal Progress", size="5"),
                        rx.spacer(),
                        rx.text(
                            AppState.daily_progress_display,
                            " of ",
                            AppState.daily_target_display,
                            size="3",
                            color="gray",
                        ),
                        width="100%",
                        align_items="center",
                    ),
                    rx.progress(
                        value=AppState.daily_progress_pct.to(int),
                        color_scheme="green",
                        width="100%",
                        height="12px"
                    ),
                    width="100%",
                    spacing="3",
                ),
                size="3",
                width="100%",
            ),

            rx.box(margin_top="1em"),

            # ── Guardian Floor Status ─────────────────────────────────────────
            rx.card(
                rx.vstack(
                    rx.heading("Guardian Floor Status", size="5", margin_bottom="0.5em"),
                    rx.hstack(
                        rx.icon("shield-check", color="var(--green-9)"),
                        rx.text("Guardian Floor Active", weight="bold"),
                        rx.spacer(),
                        rx.badge("PROTECTED", color_scheme="green", variant="soft"),
                        width="100%",
                    ),
                    width="100%"
                ),
                size="3",
                width="100%",
                background="rgba(16, 185, 129, 0.1)",
            ),

            rx.box(margin_top="1em"),

            # ── Daily Profit Ledger ───────────────────────────────────────────
            rx.card(
                rx.vstack(
                    rx.hstack(
                        rx.icon("calendar", color="var(--blue-9)"),
                        rx.heading("Daily Profit Ledger", size="5"),
                        width="100%",
                        align_items="center",
                        spacing="2",
                    ),
                    rx.table.root(
                        rx.table.body(
                            rx.foreach(AppState.daily_history_display, ledger_row),
                        ),
                        width="100%",
                        variant="surface",
                    ),
                    width="100%",
                    spacing="3",
                ),
                size="3",
                width="100%",
            ),

            rx.box(margin_top="1em"),

            # ── Mode Banner ───────────────────────────────────────────────────
            rx.cond(
                AppState.is_live,
                rx.card(
                    rx.hstack(
                        rx.icon("alert-triangle", color="var(--red-9)"),
                        rx.text("⚠️ LIVE TRADING ACTIVE — Real funds at risk", weight="bold", color="var(--red-11)"),
                        rx.spacer(),
                        rx.button(
                            "Switch to Paper",
                            on_click=AppState.go_paper,
                            color_scheme="gray",
                            variant="soft",
                            size="2",
                        ),
                        width="100%",
                    ),
                    size="3",
                    width="100%",
                    background="rgba(239, 68, 68, 0.1)",
                ),
                rx.card(
                    rx.hstack(
                        rx.icon("flask-conical", color="var(--green-9)"),
                        rx.text("Paper Trading Mode — No real funds at risk", weight="bold", color="var(--green-11)"),
                        rx.spacer(),
                        rx.badge("PAPER", color_scheme="green", variant="soft"),
                        width="100%",
                    ),
                    size="3",
                    width="100%",
                    background="rgba(16, 185, 129, 0.05)",
                ),
            ),

            width="100%",
            max_width="1200px",
            spacing="4",
        )
    )
