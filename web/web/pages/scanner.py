import reflex as rx
from web.state import AppState
from web.pages.layout import dashboard_layout

@rx.page(route="/scanner", title="Scanner Gems", on_load=AppState.load_data)
def scanner() -> rx.Component:
    return dashboard_layout(
        rx.vstack(
            rx.heading("Moralis Discovery Scanner", size="8", weight="bold"),
            rx.text("Live feed of high-momentum tokens from the Moralis API.", color="gray"),
            
            rx.divider(margin_y="1em", opacity="0.2"),
            
            rx.box(
                rx.text("Awaiting next scan cycle...", color="gray"),
                padding="2em",
                border="1px dashed rgba(255,255,255,0.2)",
                border_radius="12px",
                width="100%",
                text_align="center"
            ),
            
            width="100%",
            max_width="1200px",
            spacing="4"
        )
    )
