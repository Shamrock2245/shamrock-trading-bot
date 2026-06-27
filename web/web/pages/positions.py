"""Positions page — displays active trading positions."""
import reflex as rx
from web.state import AppState
from web.pages.layout import dashboard_layout


def position_card(pos: dict) -> rx.Component:
    """A card displaying a single active position."""
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.vstack(
                    rx.hstack(
                        rx.text(pos["token_symbol"], weight="bold", size="4"),
                        rx.badge(
                            pos["chain"].upper(),
                            color_scheme="blue",
                            variant="soft",
                            size="1",
                        ),
                        spacing="2",
                        align_items="center",
                    ),
                    rx.text(
                        "Entry: $",
                        pos["entry_price"],
                        color="gray",
                        size="2",
                    ),
                    spacing="1",
                ),
                rx.spacer(),
                rx.vstack(
                    rx.text("Unrealized P&L", size="2", color="gray", text_align="right"),
                    rx.text(
                        pos["unrealized_pnl_pct"] + "%",
                        weight="bold",
                        size="4",
                        color=rx.cond(
                            pos["is_profit"] == "true",
                            "var(--green-9)",
                            "var(--red-9)",
                        ),
                        text_align="right",
                    ),
                    spacing="1",
                ),
                width="100%",
                align_items="flex-start",
            ),
            rx.divider(margin_y="0.75em", opacity="0.2"),
            rx.hstack(
                rx.text(
                    "Score: ",
                    pos["gem_score"],
                    size="2",
                    color="gray",
                ),
                rx.spacer(),
                rx.button(
                    "Manual Sell",
                    on_click=AppState.manual_sell(pos["token_address"], 0.0),
                    color_scheme="red",
                    variant="soft",
                    size="2",
                ),
                width="100%",
            ),
            width="100%",
        ),
        size="3",
        width="100%",
    )


@rx.page(route="/positions", title="Positions", on_load=AppState.load_data)
def positions() -> rx.Component:
    return dashboard_layout(
        rx.vstack(
            rx.hstack(
                rx.vstack(
                    rx.heading("Active Positions", size="8", weight="bold"),
                    rx.text(
                        AppState.open_positions_count_display,
                        " open positions",
                        color="gray",
                        size="3",
                    ),
                    spacing="1",
                ),
                rx.spacer(),
                rx.button(
                    rx.icon("refresh-cw", size=16),
                    "Refresh",
                    on_click=AppState.load_data,
                    color_scheme="gray",
                    variant="soft",
                    size="3",
                ),
                width="100%",
                align_items="center",
            ),
            rx.divider(margin_y="1em", opacity="0.2"),

            # Show positions or empty state
            rx.cond(
                AppState.open_positions_count > 0,
                rx.vstack(
                    rx.foreach(
                        AppState.open_positions,
                        position_card,
                    ),
                    width="100%",
                    spacing="3",
                ),
                rx.box(
                    rx.vstack(
                        rx.icon("inbox", size=48, color="gray"),
                        rx.text(
                            "No active positions",
                            weight="bold",
                            size="4",
                            color="gray",
                        ),
                        rx.text(
                            "The bot will open positions when high-scoring gems are discovered.",
                            color="gray",
                            size="2",
                            text_align="center",
                        ),
                        spacing="2",
                        align_items="center",
                    ),
                    padding="3em",
                    border="1px dashed rgba(255,255,255,0.2)",
                    border_radius="12px",
                    width="100%",
                    text_align="center",
                ),
            ),

            width="100%",
            max_width="1200px",
            spacing="4",
        )
    )
