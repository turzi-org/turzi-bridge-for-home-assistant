"""Panel registration for Turzi App Connector."""

import os
import logging

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig

from .const import (
    CUSTOM_COMPONENTS,
    DOMAIN,
    INTEGRATION_FOLDER,
    PANEL_FILENAME,
    PANEL_FOLDER,
    PANEL_ICON,
    PANEL_NAME,
    PANEL_TITLE,
    PANEL_URL,
)

_LOGGER = logging.getLogger(__name__)


async def async_register_panel(hass) -> None:
    """Register the Turzi sidebar panel."""
    root_dir = os.path.join(hass.config.path(CUSTOM_COMPONENTS), INTEGRATION_FOLDER)
    panel_dir = os.path.join(root_dir, PANEL_FOLDER)
    js_path = os.path.join(panel_dir, PANEL_FILENAME)

    try:
        cache_bust = int(os.path.getmtime(js_path))
    except OSError:
        cache_bust = 0

    await hass.http.async_register_static_paths(
        [StaticPathConfig(PANEL_URL, js_path, cache_headers=False)]
    )

    await panel_custom.async_register_panel(
        hass,
        webcomponent_name=PANEL_NAME,
        frontend_url_path=DOMAIN,
        module_url=f"{PANEL_URL}?v={cache_bust}",
        sidebar_title=PANEL_TITLE,
        sidebar_icon=PANEL_ICON,
        require_admin=True,
        config={},
        config_panel_domain=DOMAIN,
    )
    _LOGGER.debug("Registered Turzi panel at %s", PANEL_URL)


def async_unregister_panel(hass) -> None:
    """Unregister the Turzi sidebar panel."""
    frontend.async_remove_panel(hass, DOMAIN)
    _LOGGER.debug("Unregistered Turzi panel")
