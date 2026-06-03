import reflex as rx
from web.state import AppState
from web.pages.auth import auth_page

def sidebar() -> rx.Component:
    return rx.vstack(
        rx.heading("SHAMROCK", size="6", weight="bold", color="var(--accent-9)", margin_bottom="1em"),
        
        rx.link(
            rx.hstack(rx.icon("layout-dashboard"), rx.text("Command Center")),
            href="/",
            padding="12px",
            border_radius="8px",
            width="100%",
            _hover={"bg": "rgba(255,255,255,0.05)"}
        ),
        rx.link(
            rx.hstack(rx.icon("activity"), rx.text("Scanner Gems")),
            href="/scanner",
            padding="12px",
            border_radius="8px",
            width="100%",
            _hover={"bg": "rgba(255,255,255,0.05)"}
        ),
        rx.link(
            rx.hstack(rx.icon("briefcase"), rx.text("Positions")),
            href="/positions",
            padding="12px",
            border_radius="8px",
            width="100%",
            _hover={"bg": "rgba(255,255,255,0.05)"}
        ),
        
        rx.spacer(),
        
        rx.vstack(
            rx.text("Trading Mode", size="2", color="gray"),
            rx.cond(
                AppState.is_live,
                rx.badge("🔴 LIVE ON-CHAIN", color_scheme="red", size="2", variant="solid"),
                rx.badge("🟢 PAPER MODE", color_scheme="green", size="2", variant="solid"),
            ),
            rx.button(
                "Switch to Live",
                on_click=lambda: AppState.go_live("CONFIRM_LIVE"),
                color_scheme="red",
                variant="outline",
                size="1",
                width="100%",
                margin_top="0.5em"
            ),
            width="100%",
            padding="12px",
            border_top="1px solid rgba(255,255,255,0.1)",
        ),
        
        width="250px",
        height="100vh",
        padding="1em",
        border_right="1px solid rgba(255,255,255,0.1)",
        background="rgba(10, 10, 10, 0.8)",
        position="fixed",
        left="0",
        top="0"
    )

def dashboard_layout(*children, **kwargs) -> rx.Component:
    """The layout for the authenticated dashboard."""
    content = rx.hstack(
        sidebar(),
        rx.box(
            *children,
            margin_left="250px",
            padding="2em",
            width="calc(100% - 250px)",
            min_height="100vh",
        ),
        width="100%",
        align_items="flex-start",
        background="radial-gradient(circle at top right, #0a1118 0%, #000000 100%)",
        color="white"
    )
    
    return rx.cond(
        AppState.is_authenticated,
        content,
        auth_page()
    )
