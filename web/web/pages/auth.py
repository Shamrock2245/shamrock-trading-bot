import reflex as rx
from web.state import AppState

def auth_page() -> rx.Component:
    return rx.center(
        rx.vstack(
            rx.heading("SHAMROCK TRADING", size="8", weight="bold", color="var(--accent-9)"),
            rx.text("Enter your PIN to continue", size="3", color="gray", margin_bottom="1em"),
            
            rx.cond(
                AppState.auth_error != "",
                rx.callout(AppState.auth_error, icon="triangle_alert", color_scheme="red", margin_bottom="1em"),
            ),
            
            rx.input(
                placeholder="Enter PIN",
                type="password",
                input_mode="numeric",
                on_change=AppState.set_password,
                id="password_input",
                size="3",
                width="100%",
                style={"border_radius": "8px", "background": "rgba(255,255,255,0.05)", "text_align": "center", "letter_spacing": "0.3em", "font_size": "1.2em"}
            ),
            
            rx.button(
                "Unlock", 
                on_click=lambda: AppState.check_auth(AppState.password),
                size="3",
                width="100%",
                color_scheme="green",
                variant="solid",
                style={"border_radius": "8px"}
            ),
            
            spacing="4",
            padding="2em",
            border="1px solid rgba(255,255,255,0.1)",
            border_radius="16px",
            background="rgba(10, 10, 10, 0.6)",
            backdrop_filter="blur(10px)",
            box_shadow="0 8px 32px 0 rgba(0, 0, 0, 0.37)",
            align_items="center",
            width="400px",
        ),
        width="100vw",
        height="100vh",
        background="radial-gradient(circle at center, #111111 0%, #000000 100%)"
    )
