import reflex as rx
from web.state import AppState
from web.pages.layout import dashboard_layout

def stat_card(title: str, value: str, icon: str, color: str) -> rx.Component:
    return rx.hstack(
        rx.box(
            rx.icon(icon, size=24, color=color),
            padding="12px",
            background=f"var(--{color}-3)",
            border_radius="12px",
        ),
        rx.vstack(
            rx.text(title, size="2", color="gray"),
            rx.text(value, size="5", weight="bold"),
            spacing="1",
        ),
        padding="1.5em",
        background="rgba(255,255,255,0.03)",
        border="1px solid rgba(255,255,255,0.05)",
        border_radius="16px",
        width="100%",
        box_shadow="0 4px 12px rgba(0,0,0,0.1)",
        align_items="center",
        spacing="4",
    )

@rx.page(route="/", title="Command Center", on_load=AppState.load_data)
def index() -> rx.Component:
    return dashboard_layout(
        rx.vstack(
            rx.hstack(
                rx.heading("Command Center", size="8", weight="bold"),
                rx.spacer(),
                rx.button(
                    rx.icon("refresh-cw", size=16),
                    "Force Moralis Scan",
                    on_click=AppState.force_scan,
                    color_scheme="blue",
                    variant="soft",
                    size="3"
                ),
                width="100%",
                align_items="center"
            ),
            
            rx.divider(margin_y="1em", opacity="0.2"),
            
            # Key Stats Row
            rx.grid(
                stat_card(
                    "Total P&L", 
                    rx.cond(AppState.daily_goal["total_pnl"] != None, f"${AppState.daily_goal['total_pnl']}", "$0.00"), 
                    "dollar-sign", 
                    "green"
                ),
                stat_card(
                    "Win Rate", 
                    rx.cond(AppState.daily_goal["win_rate"] != None, f"{AppState.daily_goal['win_rate']}%", "0%"), 
                    "trending-up", 
                    "blue"
                ),
                stat_card(
                    "Active Positions", 
                    rx.cond(AppState.positions["total_active"] != None, f"{AppState.positions['total_active']}", "0"), 
                    "briefcase", 
                    "purple"
                ),
                stat_card(
                    "Scanner Gems", 
                    "Active", 
                    "radar", 
                    "orange"
                ),
                columns="4",
                spacing="4",
                width="100%"
            ),
            
            rx.box(margin_top="2em"),
            
            # Guardian Status
            rx.heading("Guardian Floor Status", size="5", margin_bottom="0.5em"),
            rx.box(
                rx.hstack(
                    rx.icon("shield-check", color="var(--green-9)"),
                    rx.text("Guardian Floor Active", weight="bold"),
                    rx.spacer(),
                    rx.badge("PROTECTED", color_scheme="green", variant="soft"),
                    width="100%"
                ),
                padding="1.5em",
                background="rgba(16, 185, 129, 0.1)",
                border="1px solid rgba(16, 185, 129, 0.2)",
                border_radius="12px",
                width="100%"
            ),
            
            width="100%",
            max_width="1200px",
            spacing="4"
        )
    )
