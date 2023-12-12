
from ..zhi.entity import ZhiPollEntity, ZHI_SCHEMA
from homeassistant.components.climate import ClimateEntity, PLATFORM_SCHEMA
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_DEVICE, ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.components.climate.const import ClimateEntityFeature, HVACMode, HVACAction, PRESET_HOME, PRESET_AWAY
import homeassistant.helpers.config_validation as cv
import voluptuous as vol
import asyncio

import logging
_LOGGER = logging.getLogger(__name__)


PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(ZHI_SCHEMA | {
    vol.Required(CONF_HOST): cv.string,
    vol.Optional(CONF_PORT, default=2000): int,
    vol.Optional(CONF_DEVICE, default='1'): cv.string,
})


async def async_setup_platform(hass, conf, async_add_entities, discovery_info=None):
    async_add_entities([ZhiSaswellClimate(hass, conf)], True)


class ZhiSaswellClimate(ZhiPollEntity, ClimateEntity):

    def __init__(self, hass, conf):
        super().__init__(conf)
        self.hass = hass
        self.host = conf[CONF_HOST]
        self.port = conf[CONF_PORT]
        self.device = conf[CONF_DEVICE]
        self._attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.PRESET_MODE
        self._attr_preset_modes = [PRESET_HOME, PRESET_AWAY]
        self._attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_target_temperature_step = 0.5

    async def async_set_temperature(self, **kwargs):
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is not None:
            await self.async_command('S44', temperature)

    async def async_set_hvac_mode(self, hvac_mode):
        await self.async_command('S41', '1' if hvac_mode == HVACMode.HEAT else '0')

    async def async_set_preset_mode(self, preset_mode):
        # await self.async_command('S41', '1' if preset_mode == PRESET_AWAY else '0')
        _LOGGER.warn("TODO: Not implement")

    async def async_command(self, command, value):
        if self.data is None:
            _LOGGER.error("Topic not ready")
            return
        self.skip_poll = True
        message = f'/{self.data}/{command}/{self.device}/{value}\n'
        _LOGGER.debug("Send message: " + message)
        await self.async_poll(message)

    async def async_poll(self, message=None):
        reader, writer = await asyncio.open_connection(self.host, self.port)
        if message is not None:
            writer.write(message.encode())
        while chunk := await reader.read(1024):
            lines = chunk.decode().split('\n')
            for line in lines:
                if len(line) < 1 or line[0] != '/':
                    # _LOGGER.error("Exception topic: " + line)
                    continue
                parts = line[1:].split('/')
                if len(parts) < 4 or parts[1] != 'S00' or '/'.join(parts[2:-1]) != self.device:
                    _LOGGER.debug("Skip topic: " + line)
                    continue
                status = parts[-1].split(',')
                if len(status) < 11:
                    _LOGGER.error("Exception status: " + line)
                    continue
                _LOGGER.debug(line)
                self._attr_hvac_mode = HVACMode.HEAT if status[0] == '1' else HVACMode.OFF
                self._attr_hvac_action = HVACAction.HEATING if status[0] == '1' else HVACAction.OFF
                self._attr_current_temperature = float(status[1])
                self._attr_target_temperature = float(status[2])
                self._attr_preset_mode = PRESET_AWAY if status[4] == '1' else PRESET_HOME
                self._attr_min_temp = float(status[9])
                self._attr_max_temp = float(status[10])
                writer.close()
                await writer.wait_closed()
                return parts[0]
        writer.close()
        await writer.wait_closed()
        return None
