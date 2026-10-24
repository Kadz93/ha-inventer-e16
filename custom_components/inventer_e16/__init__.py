# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Tobias Krautkremer
"""inVENTer Easy Connect e16 - local control over Wi-Fi (TLS-PSK)."""
from homeassistant.const import Platform
from homeassistant.helpers import device_registry as dr

from . import coordinator
from .const import CONF_DEVICE_ID, CONF_FIRMWARE_CATALOG, DOMAIN

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.FAN, Platform.BUTTON,
             Platform.NUMBER, Platform.SELECT, Platform.UPDATE]


async def async_migrate_entry(hass, entry):
    """1.1 -> 1.2: the firmware catalog became opt-in. Entries that never stored the option had it
    on, so store that explicitly - an update must not silently switch it off."""
    if entry.version > 1:
        return False
    if entry.minor_version < 2:
        options = {CONF_FIRMWARE_CATALOG: True, **entry.options}
        hass.config_entries.async_update_entry(entry, options=options, minor_version=2)
    return True


async def async_setup_entry(hass, entry):
    data = coordinator.create(hass, entry)
    await data.zones[0].async_config_entry_first_refresh()
    # Discover additional zones (indices 1..7)
    client = data.zones[0].client
    for index in range(1, 8):
        try:
            zone_data = await hass.async_add_executor_job(client.get_zone, index)
        except (OSError, ValueError):
            break
        if not zone_data.get("zone_id") or zone_data["zone_id"] in [z.data["zone_id"] for z in data.zones if z.data]:
            break
        zone_coord = coordinator.E16ZoneCoordinator(hass, entry, client, index)
        zone_coord.async_set_updated_data(zone_data)
        data.zones.append(zone_coord)
    await data.info.async_config_entry_first_refresh()
    # Create the main device first: fans and sensors reference it via via_device_id
    data.main_device_id = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, entry.data[CONF_DEVICE_ID])},
        name=entry.title, manufacturer="inVENTer", model="Easy Connect e16",
    ).id
    # Create zone devices for multi-zone setups (zone 2+)
    if len(data.zones) > 1:
        device_id = entry.data[CONF_DEVICE_ID]
        for zone_coord in data.zones[1:]:
            zone_data = zone_coord.data
            dr.async_get(hass).async_get_or_create(
                config_entry_id=entry.entry_id,
                identifiers={(DOMAIN, f"{device_id}_z{zone_data['zone_id']}")},
                name=f"inVENTer {zone_data['name']}" if zone_data.get("name") else f"inVENTer Zone {zone_data['zone_id']}",
                manufacturer="inVENTer", model="Easy Connect e16",
                via_device_id=data.main_device_id,
            )
    entry.runtime_data = data
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # No update listener: it would reload on every entry change, even when Home Assistant only
    # records a DHCP discovery key. Options reload via OptionsFlowWithReload, flows via their abort.
    return True


async def async_unload_entry(hass, entry):
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
