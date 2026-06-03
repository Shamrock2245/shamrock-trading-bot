import reflex as rx
from web.state import AppState
from web.pages.layout import dashboard_layout

def position_card(pos: dict) -> rx.Component:
    """A card displaying a single active position."""
    # Dummy parsing for now
    token = "UNKNOWN"
    pnl = "$0.00"
    pnl_color = "gray"
    
    return rx.box(
        rx.hstack(
            rx.vstack(
                rx.text(token, weight="bold", size="4"),
                rx.text("Status: Active", color="green", size="2"),
                spacing="1"
            ),
            rx.spacer(),
            rx.vstack(
                rx.text("Unrealized P&L", size="2", color="gray", text_align="right"),
                rx.text(pnl, weight="bold", size="4", color=f"var(--{pnl_color}-9)", text_align="right"),
                spacing="1"
            ),
        ),
        rx.divider(margin_y="1em", opacity="0.2"),
        rx.hstack(
            rx.button(
                "Manual Sell", 
                on_click=lambda: AppState.manual_sell(pos.get("address", ""), 0.0),
                color_scheme="red", 
                variant="soft",
                size="2"
            ),
        ),
        padding="1.5em",
        background="rgba(255,255,255,0.03)",
        border="1px solid rgba(255,255,255,0.05)",
        border_radius="16px",
        width="100%",
        box_shadow="0 4px 12px rgba(0,0,0,0.1)",
    )

@rx.page(route="/positions", title="Positions", on_load=AppState.load_data)
def positions() -> rx.Component:
    return dashboard_layout(
        rx.vstack(
            rx.heading("Active Positions", size="8", weight="bold"),
            rx.text("Monitor and manage your active trading positions.", color="gray"),
            
            rx.divider(margin_y="1em", opacity="0.2"),
            
            # This would iterate over AppState.positions if it's a list. 
            # For now, we just display a placeholder message if empty.
            rx.cond(
                True, # AppState.positions is actually a dict in the bot, we'll just show UI shell
                rx.box(
                    rx.text("No active positions currently loaded.", color="gray"),
                    padding="2em",
                    border="1px dashed rgba(255,255,255,0.2)",
                    border_radius="12px",
                    width="100%",
                    text_align="center"
                )
            ),
            
            width="100%",
            max_width="1200px",
            spacing="4"
        )
    )
