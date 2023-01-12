from datetime import timedelta
from homeassistant.components.climate import ClimateEntity, PLATFORM_SCHEMA
from homeassistant.components.climate.const import SUPPORT_TARGET_TEMPERATURE, SUPPORT_PRESET_MODE, ATTR_HVAC_MODE, HVAC_MODE_HEAT, HVAC_MODE_OFF, CURRENT_HVAC_HEAT, CURRENT_HVAC_OFF, ATTR_CURRENT_TEMPERATURE, ATTR_PRESET_MODE, PRESET_HOME, PRESET_AWAY
from homeassistant.const import ATTR_ID, ATTR_NAME, CONF_USERNAME, CONF_PASSWORD, CONF_SCAN_INTERVAL, ATTR_TEMPERATURE
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import STORAGE_DIR
import homeassistant.helpers.config_validation as cv
import logging
import time
import voluptuous as vol

_LOGGER = logging.getLogger(__name__)

DOMAIN = "zhisaswell"
USER_AGENT = "Thermostat/3.1.0 (iPhone; iOS 11.3; Scale/3.00)"

AUTH_URL = "http://api.scinan.com/oauth2/authorize?client_id=100002&passwd=%s&redirect_uri=http%%3A//localhost.com%%3A8080/testCallBack.action&response_type=token&userId=%s"
LIST_URL = "http://api.scinan.com/v1.0/devices/list?format=json"
CTRL_URL = "http://api.scinan.com/v1.0/sensors/control?control_data=%%7B%%22value%%22%%3A%%22%s%%22%%7D&device_id=%s&format=json&sensor_id=%s&sensor_type=1"

DEFAULT_NAME = 'Saswell'
ATTR_AVAILABLE = 'available'

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_USERNAME): cv.string,
    vol.Required(CONF_PASSWORD): cv.string,
    vol.Optional(CONF_SCAN_INTERVAL, default=timedelta(seconds=300)): vol.All(cv.time_period, cv.positive_timedelta)
})


async def async_setup_platform(hass, conf, async_add_entities, discovery_info=None):
    saswell = SaswellData(hass, conf[CONF_USERNAME], conf[CONF_PASSWORD])
    await saswell.update_data()
    if not saswell.devs:
        _LOGGER.error("No sensors added.")
        return

    saswell.devices = [ZhiSaswellClimate(saswell, index) for index in range(len(saswell.devs))]
    async_add_entities(saswell.devices)
    async_track_time_interval(hass, saswell.async_update, conf.get(CONF_SCAN_INTERVAL))


class ZhiSaswellClimate(ClimateEntity):
    """Representation of a Saswell climate device."""

    def __init__(self, saswell, index):
        """Initialize the climate device."""
        self._index = index
        self._saswell = saswell

    @property
    def unique_id(self):
        from homeassistant.util import slugify
        return self.__class__.__name__.lower() + '.' + slugify(self.name)

    @property
    def name(self):
        """Return the name of the climate device."""
        return self.get_value(ATTR_NAME)

    @property
    def available(self):
        """Return if the sensor data are available."""
        return self.get_value(ATTR_AVAILABLE)

    @property
    def supported_features(self):
        """Return the list of supported features."""
        return SUPPORT_TARGET_TEMPERATURE | SUPPORT_PRESET_MODE

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return self._saswell._hass.config.units.temperature_unit

    @property
    def target_temperature_step(self):
        """Return the supported step of target temperature."""
        return 1

    @property
    def current_temperature(self):
        """Return the current temperature."""
        return self.get_value(ATTR_CURRENT_TEMPERATURE)

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self.get_value(ATTR_TEMPERATURE)

    @property
    def hvac_action(self):
        """Return current operation ie. heat, cool, idle."""
        return CURRENT_HVAC_HEAT if self.hvac_mode == HVAC_MODE_HEAT else CURRENT_HVAC_OFF

    @property
    def hvac_mode(self):
        """Return hvac target hvac state."""
        return self.get_value(ATTR_HVAC_MODE)

    @property
    def hvac_modes(self):
        """Return the list of available operation modes."""
        return [HVAC_MODE_HEAT, HVAC_MODE_OFF]

    @property
    def preset_mode(self):
        """Return preset mode."""
        return self.get_value(ATTR_PRESET_MODE)

    @property
    def preset_modes(self):
        """Return preset modes."""
        return [PRESET_HOME, PRESET_AWAY]

    @property
    def should_poll(self):  # pylint: disable=no-self-use
        """No polling needed."""
        return False

    async def async_set_temperature(self, **kwargs):
        """Set new target temperatures."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is not None:
            await self.set_value(ATTR_TEMPERATURE, temperature)

    async def async_set_hvac_mode(self, hvac_mode):
        """Set new target temperature."""
        await self.set_value(ATTR_HVAC_MODE, hvac_mode)

    async def async_set_preset_mode(self, preset_mode):
        """Update preset_mode on."""
        await self.set_value(ATTR_PRESET_MODE, preset_mode)

    def get_value(self, prop):
        """Get property value"""
        devs = self._saswell.devs
        if devs and self._index < len(devs):
            return devs[self._index][prop]
        return None

    async def set_value(self, prop, value):
        """Set property value"""
        if await self._saswell.control(self._index, prop, value):
            await self.async_update_ha_state()


class SaswellData():
    """Class for handling the data retrieval."""

    def __init__(self, hass, username, password):
        """Initialize the data object."""
        self._hass = hass
        self._username = username.replace('@', '%40')
        self._password = password
        self._token_path = hass.config.path(STORAGE_DIR, DOMAIN)
        self.devs = None

        try:
            with open(self._token_path) as file:
                self._token = file.read()
                _LOGGER.debug("Load token: %s", self._token_path)
        except Exception:
            self._token = None

    async def async_update(self, time):
        """Update online data and update ha state."""
        old_devs = self.devs
        await self.update_data()

        tasks = []
        index = 0
        for device in self.devices:
            if not old_devs or not self.devs or old_devs[index] != self.devs[index]:
                _LOGGER.info('%s: => %s', device.name, device.state)
                await device.async_update_ha_state()

    async def update_data(self):
        """Update online data."""
        try:
            json = await self.request(LIST_URL)
            if ('error' in json) and (json['error'] != '0'):
                _LOGGER.debug("Reset token: error=%s", json['error'])
                self._token = None
                json = await self.request(LIST_URL)
            devs = []
            for dev in json:
                if not isinstance(dev, dict):
                    raise TypeError(f"{json}")
                status = dev['status'].split(',')
                devs.append({ATTR_HVAC_MODE: HVAC_MODE_HEAT if status[1] == '1' else HVAC_MODE_OFF,
                             ATTR_PRESET_MODE: PRESET_AWAY if status[5] == '1' else PRESET_HOME,
                             ATTR_CURRENT_TEMPERATURE: float(status[2]),
                             ATTR_TEMPERATURE: float(status[3]),
                             ATTR_AVAILABLE: dev['online'] == '1',
                             ATTR_NAME: dev['title'],
                             ATTR_ID: dev['id']})
            self.devs = devs
            _LOGGER.debug("List device: devs=%s", self.devs)
        except Exception:
            import traceback
            _LOGGER.error(traceback.format_exc())

    async def control(self, index, prop, value):
        """Control device via server."""
        try:
            if prop == ATTR_HVAC_MODE:
                sensor_id = '01'
                data = '1' if value == HVAC_MODE_HEAT else '0'
            elif prop == ATTR_TEMPERATURE:
                sensor_id = '02'
                data = value
            elif prop == ATTR_PRESET_MODE:
                sensor_id = '03'
                data = '1' if value == PRESET_AWAY else '0'
            else:
                return False

            device_id = self.devs[index]['id']
            json = await self.request(CTRL_URL % (data, device_id, sensor_id))
            _LOGGER.debug("Control device: prop=%s, json=%s", prop, json)
            if json['result']:
                self.devs[index][prop] = value
                return True
            return False
        except Exception:
            import traceback
            _LOGGER.error('Exception: %s', traceback.format_exc())
            return False

    async def request(self, url):
        """Request from server."""
        session = self._hass.helpers.aiohttp_client.async_get_clientsession()
        if self._token is None:
            headers = {'User-Agent': USER_AGENT}
            auth_url = AUTH_URL % (self._password, self._username)
            _LOGGER.debug("AUTH: %s", auth_url)
            async with await session.get(auth_url, headers=headers) as r:
                text = await r.text()
            #_LOGGER.info("Get token: %s", text)
            start = text.find('token:')
            if start == -1:
                return None

            start += 6
            end = text.find('\n', start) - 1
            self._token = text[start:end]
            with open(self._token_path, 'w') as file:
                file.write(self._token)

        headers = {'User-Agent': USER_AGENT}
        url += "&timestamp=%s&token=%s" % (time.strftime('%Y-%m-%d%%20%H%%3A%M%%3A%S'), self._token)
        _LOGGER.debug("URL: %s", url)
        async with await session.get(url, headers=headers) as r:
            # _LOGGER.debug("RESPONSE: %s", await r.text())
            return await r.json(content_type=None)
