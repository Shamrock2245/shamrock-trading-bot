"""Main application routing for the Shamrock Trading Bot Dashboard."""

import reflex as rx
from web.state import AppState

# Import all pages
from web.pages.dashboard import index
from web.pages.positions import positions
from web.pages.scanner import scanner
from web.pages.auth import auth_page

# Create app instance and configure theme
app = rx.App(
    theme=rx.theme(
        appearance="dark",
        has_background=True,
        radius="large",
        accent_color="green",
    ),
    stylesheets=[
        "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap",
    ],
    style={
        "font_family": "Inter, sans-serif",
    }
)


