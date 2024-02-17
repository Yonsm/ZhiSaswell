
from ..zhi.entity import ZhiPollEntity, ZHI_SCHEMA
from homeassistant.components.climate import ClimateEntity, PLATFORM_SCHEMA
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_DEVICE, CONF_SENSOR_TYPE, ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.components.climate.const import ClimateEntityFeature, HVACMode, HVACAction, PRESET_HOME, PRESET_AWAY
from homeassistant.util import slugify
import homeassistant.helpers.config_validation as cv
import voluptuous as vol
import asyncio

import logging
_LOGGER = logging.getLogger(__name__)

CONF_SENSOR_NAMES = 'sensor_names'
CONF_SENSOR_STATUS = 'sensor_status'
CONF_SENSOR_HVAC_MODE = 'sensor_hvac_mode'
CONF_SENSOR_TEMPERATURE = 'sensor_temperature'
CONF_SENSOR_PRESET_MODE = 'sensor_preset_mode'


PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(ZHI_SCHEMA | {
    vol.Required(CONF_HOST): cv.string,
    vol.Optional(CONF_PORT, default=2000): int,
    vol.Optional(CONF_DEVICE): cv.string,
    vol.Optional(CONF_SENSOR_NAMES): list,
    vol.Optional(CONF_SENSOR_TYPE, default=['1']): vol.Any(cv.string, list),
    vol.Optional(CONF_SENSOR_STATUS, default='S00'): cv.string,
    vol.Optional(CONF_SENSOR_HVAC_MODE, default='S01'): cv.string,
    vol.Optional(CONF_SENSOR_TEMPERATURE, default='S02'): cv.string,
    vol.Optional(CONF_SENSOR_PRESET_MODE, default='S03'): cv.string,
})


async def async_setup_platform(hass, conf, async_add_entities, discovery_info=None):
    types = conf[CONF_SENSOR_TYPE]
    if not isinstance(types, list):
        types = [types]
    async_add_entities([ZhiSaswellClimate(conf, x) for x in types], True)


class ZhiSaswellClimate(ZhiPollEntity, ClimateEntity):

    def __init__(self, conf, sensor_type):
        super().__init__(conf)
        if names := conf.get(CONF_SENSOR_NAMES):
            self._attr_name = names[conf[CONF_SENSOR_TYPE].index(sensor_type)]
            self._attr_unique_id = slugify(self._attr_name)
        self.host = conf[CONF_HOST]
        self.port = conf[CONF_PORT]
        self.sensor_type = sensor_type
        self.device = conf.get(CONF_DEVICE)
        self.sensor_status = conf[CONF_SENSOR_STATUS]
        self.sensor_hvac_mode = conf[CONF_SENSOR_HVAC_MODE]
        self.sensor_temperature = conf[CONF_SENSOR_TEMPERATURE]
        self.sensor_preset_mode = conf[CONF_SENSOR_PRESET_MODE]
        self._attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
        if self.sensor_preset_mode:
            self._attr_supported_features |= ClimateEntityFeature.PRESET_MODE
        self._attr_preset_modes = [PRESET_HOME, PRESET_AWAY]
        self._attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_target_temperature_step = 0.5

    async def async_set_temperature(self, **kwargs):
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is not None:
            await self.async_control(self.sensor_temperature, temperature)

    async def async_set_hvac_mode(self, hvac_mode):
        await self.async_control(self.sensor_hvac_mode, '1' if hvac_mode == HVACMode.HEAT else '0')

    async def async_set_preset_mode(self, preset_mode):
        await self.async_control(self.sensor_preset_mode, '1' if preset_mode == PRESET_AWAY else '0')

    async def async_control(self, sensor_id, value):
        if self.device is None:
            _LOGGER.error("Device not ready")
            return
        self.skip_poll = True
        command = f'/{self.device}/{sensor_id}/{self.sensor_type}/{value}\n'
        await self.async_poll(command)
        self.async_write_ha_state()

    async def async_poll(self, command=None):
        reader, writer = await asyncio.open_connection(self.host, self.port)
        if command is not None:
            _LOGGER.debug("Send command: " + command)
            await reader.read(1024)  # Receive dummy
            writer.write(command.encode())
            await asyncio.sleep(0.3)
        if self.device is not None:
            polling = f'/{self.device}/{self.sensor_status}/{self.sensor_type}\n'
            _LOGGER.debug("Send polling: " + polling)
            writer.write(polling.encode())
        while chunk := await reader.read(1024):
            lines = chunk.decode().split('\n')
            for line in lines:
                if len(line) < 1 or line[0] != '/':
                    # _LOGGER.error("Exception topic: " + line)
                    continue
                parts = line[1:].split('/')
                if self.device is None:
                    self.device = parts[0]
                elif self.device != parts[0]:
                    _LOGGER.error("Device mis-match: " + line)
                    continue
                if len(parts) < 4 or parts[1] != self.sensor_status or '/'.join(parts[2:-1]) != self.sensor_type:
                    _LOGGER.debug("Not status topic: " + line)
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
                return True
        writer.close()
        await writer.wait_closed()
        return None
