"""Scanner Gems page — live feed from Moralis discovery pipeline."""
import reflex as rx
from web.state import AppState
from web.pages.layout import dashboard_layout


def gem_row(gem: dict) -> rx.Component:
    """A row in the scanner gems table."""
    return rx.table.row(
        rx.table.cell(
            rx.hstack(
                rx.text(gem["symbol"], weight="bold"),
                rx.badge(
                    gem["chain"].upper(),
                    color_scheme="blue",
                    variant="soft",
                    size="1",
                ),
                spacing="2",
                align_items="center",
            )
        ),
        rx.table.cell(
            rx.text(
                gem["gem_score"],
                color=gem["score_color"],
                weight="bold",
            )
        ),
        rx.table.cell(rx.text(gem["source"], size="2", color="gray")),
        rx.table.cell(
            rx.text(
                "$" + gem["price_usd"],
                size="2",
            )
        ),
        rx.table.cell(
            rx.text(
                "$" + gem["volume_24h"] + "k",
                size="2",
                color="gray",
            )
        ),
    )


@rx.page(route="/scanner", title="Scanner Gems", on_load=AppState.load_data)
def scanner() -> rx.Component:
    return dashboard_layout(
        rx.vstack(
            rx.hstack(
                rx.vstack(
                    rx.heading("Moralis Discovery Scanner", size="8", weight="bold"),
                    rx.text(
                        AppState.scanner_gems_count_display,
                        " gems in queue",
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
                rx.button(
                    rx.icon("zap", size=16),
                    "Force Scan",
                    on_click=AppState.force_scan,
                    color_scheme="blue",
                    variant="soft",
                    size="3",
                ),
                width="100%",
                align_items="center",
                spacing="2",
            ),
            rx.divider(margin_y="1em", opacity="0.2"),

            # Scanner gems table or empty state
            rx.cond(
                AppState.scanner_gems_count_display != "0",
                rx.table.root(
                    rx.table.header(
                        rx.table.row(
                            rx.table.column_header_cell("Token"),
                            rx.table.column_header_cell("Score"),
                            rx.table.column_header_cell("Source"),
                            rx.table.column_header_cell("Price"),
                            rx.table.column_header_cell("24h Vol"),
                        )
                    ),
                    rx.table.body(
                        rx.foreach(AppState.scanner_gems_display, gem_row),
                    ),
                    width="100%",
                    variant="surface",
                ),
                rx.box(
                    rx.vstack(
                        rx.icon("radar", size=48, color="gray"),
                        rx.text(
                            "Awaiting next scan cycle...",
                            weight="bold",
                            size="4",
                            color="gray",
                        ),
                        rx.text(
                            "The scanner runs every 60 seconds across 6 chains.",
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
