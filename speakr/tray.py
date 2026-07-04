"""System tray icon and menu (pystray). The icon color is the app state:
gray = loading, slate = idle, red = recording, amber = processing."""

import logging

import pystray
from PIL import Image, ImageDraw

log = logging.getLogger("speakr.tray")

STATE_COLORS = {
    "loading": "#718096",
    "idle": "#2b6cb0",
    "recording": "#e53e3e",
    "processing": "#dd6b20",
    "disabled": "#4a5568",
    "error": "#805ad5",
}

MODELS = ["auto", "tiny", "base", "small", "medium", "large-v3-turbo", "large-v3"]


def _make_icon(color: str) -> Image.Image:
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((4, 4, 60, 60), fill=color)
    # Simple mic glyph: capsule + stand.
    draw.rounded_rectangle((26, 14, 38, 36), radius=6, fill="white")
    draw.arc((20, 24, 44, 44), start=0, end=180, fill="white", width=3)
    draw.line((32, 44, 32, 50), fill="white", width=3)
    draw.line((25, 50, 39, 50), fill="white", width=3)
    return img


ICONS = {state: _make_icon(color) for state, color in STATE_COLORS.items()}


class Tray:
    def __init__(self, app):
        self.app = app
        self.icon = pystray.Icon(
            "Speakr",
            icon=ICONS["loading"],
            title="Speakr — loading model...",
            menu=self._build_menu(),
        )

    def _model_item(self, name):
        # Real closures, not default-arg captures: pystray rejects callables
        # whose signature has more than (icon, item).
        return pystray.MenuItem(
            name,
            lambda icon, item: self.app.change_model(name),
            radio=True,
            checked=lambda item: self.app.config.get("model") == name,
        )

    def _build_menu(self):
        app = self.app
        model_items = [self._model_item(name) for name in MODELS]
        return pystray.Menu(
            pystray.MenuItem(
                "Enabled",
                lambda _icon, _item: app.toggle_enabled(),
                checked=lambda item: app.enabled,
            ),
            pystray.MenuItem(
                "AI formatting",
                lambda _icon, _item: app.toggle_formatting(),
                checked=lambda item: app.config.get("formatting", "enabled"),
            ),
            pystray.MenuItem(
                "Learn vocabulary",
                lambda _icon, _item: app.toggle_learning(),
                checked=lambda item: app.config.get("learning", "enabled"),
            ),
            pystray.MenuItem(
                "Screen context",
                lambda _icon, _item: app.toggle_screen_context(),
                checked=lambda item: app.config.get("screen_context", "enabled"),
            ),
            pystray.MenuItem("Model", pystray.Menu(*model_items)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Open config", lambda _icon, _item: app.open_config()),
            pystray.MenuItem("Open dictionary", lambda _icon, _item: app.open_dictionary()),
            pystray.MenuItem("Reload config", lambda _icon, _item: app.reload_config()),
            pystray.MenuItem("View log", lambda _icon, _item: app.open_log()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", lambda _icon, _item: app.quit()),
        )

    def set_state(self, state: str, detail: str = ""):
        self.icon.icon = ICONS.get(state, ICONS["idle"])
        title = f"Speakr — {state}"
        if detail:
            title += f" ({detail})"
        self.icon.title = title
        if self.icon.visible:
            self.icon.update_menu()

    def run(self):
        self.icon.run()

    def stop(self):
        self.icon.stop()
