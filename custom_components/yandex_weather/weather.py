"""
Support for the Yandex.Weather with “Weather on your site” rate.
For more details about Yandex.Weather, please refer to the documentation at
https://tech.yandex.com/weather/

"""

import asyncio
import logging
import socket

import aiohttp
import async_timeout

from datetime import timedelta

import voluptuous as vol
import homeassistant.util.dt as dt_util

from homeassistant.const import (
    UnitOfPrecipitationDepth,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
    CONF_NAME,
    CONF_API_KEY,
    CONF_LATITUDE,
    CONF_LONGITUDE,
)

from homeassistant.components.weather import (
    ATTR_FORECAST_TIME,
    ATTR_FORECAST_CONDITION,
    ATTR_FORECAST_NATIVE_TEMP,
    ATTR_FORECAST_NATIVE_TEMP_LOW,
    ATTR_FORECAST_NATIVE_PRECIPITATION,
    ATTR_FORECAST_NATIVE_WIND_SPEED,
    ATTR_FORECAST_WIND_BEARING,
    ATTR_FORECAST_NATIVE_PRESSURE,
    ATTR_WEATHER_HUMIDITY,
    PLATFORM_SCHEMA,
    WeatherEntity,
)

from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import Throttle

import homeassistant.helpers.config_validation as cv


_LOGGER = logging.getLogger(__name__)

TIME_STR_FORMAT = "%H:%M %d.%m.%Y"
DEFAULT_NAME = "Yandex Weather"
ATTRIBUTION = "Data provided by Yandex.Weather"

ATTR_FEELS_LIKE_TEMP = "feels_like"
ATTR_WEATHER_ICON = "weather_icon"
ATTR_OBSERVATION_TIME = "observation_time"
ATTR_PRECIPITATION_PROB = "precipitation_probability"

CONDITION_CLASSES = {
    "sunny": ["clear"],
    "partlycloudy": ["partly-cloudy"],
    "cloudy": ["cloudy", "overcast"],
    "pouring": ["heavy-rain", "continuous-heavy-rain", "showers", "hail"],
    "rainy": ["drizzle", "light-rain", "rain", "moderate-rain"],
    "lightning-rainy": [
        "thunderstorm",
        "thunderstorm-with-rain",
        "thunderstorm-with-hail",
    ],
    "snowy-rainy": ["wet-snow"],
    "snowy": ["light-snow", "snow", "snow-showers"],
}

MIN_TIME_BETWEEN_UPDATES = timedelta(minutes=45)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Required(CONF_API_KEY): cv.string,
        vol.Optional(CONF_LATITUDE): cv.latitude,
        vol.Optional(CONF_LONGITUDE): cv.longitude,
    }
)


def get_condition(data):
    return next(
        (k for k, v in CONDITION_CLASSES.items() if data.get("condition") in v),
        None,
    )


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the Yandex.Weather weather platform."""
    longitude = config.get(CONF_LONGITUDE, hass.config.longitude)
    latitude = config.get(CONF_LATITUDE, hass.config.latitude)
    name = config.get(CONF_NAME)
    api_key = config.get(CONF_API_KEY)
    session = async_get_clientsession(hass)

    async_add_entities(
        [YandexWeather(name, longitude, latitude, api_key, session)], True
    )


class YandexWeather(WeatherEntity):
    """Representation of a weather entity."""

    _attr_attribution = ATTRIBUTION
    _attr_should_poll = False

    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_pressure_unit = UnitOfPressure.HPA
    _attr_native_wind_speed_unit = UnitOfSpeed.METERS_PER_SECOND
    _attr_native_precipitation_unit = UnitOfPrecipitationDepth.MILLIMETERS

    def __init__(self, name: str, longitude: str, latitude: str, api_key: str, session):
        self._longitude = longitude
        self._latitude = latitude
        self._api_key = api_key
        self._session = session

        self._attr_name = name
        self._attr_unique_id = f"{name}_{longitude}_{latitude}"

        self._weather_data = YandexWeatherApi(
            self._latitude,
            self._longitude,
            self._api_key,
            session=self._session,
        )

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    async def async_update(self):
        """Get the latest weather information."""
        await self._weather_data.get_weather()

    @property
    def native_temperature(self) -> float | None:
        """Return the temperature."""
        if self._weather_data.current is not None:
            return self._weather_data.current.get("temp")
        return None

    @property
    def humidity(self) -> float | None:
        """Return the humidity."""
        if self._weather_data.current is not None:
            return self._weather_data.current.get("humidity")
        return None

    @property
    def native_wind_speed(self) -> float | None:
        """Return the wind speed."""
        if self._weather_data.current is not None:
            return self._weather_data.current.get("wind_speed")
        return None

    @property
    def wind_bearing(self) -> float | str | None:
        """Return the wind bearing."""
        if self._weather_data.current is not None:
            return self._weather_data.current.get("wind_dir")
        return None

    @property
    def native_pressure(self) -> float | None:
        """Return the pressure."""
        if self._weather_data.current is not None:
            return self._weather_data.current.get("pressure_pa")
        return None

    @property
    def condition(self) -> str | None:
        """Return the weather condition"""
        if self._weather_data.current is not None:
            return get_condition(self._weather_data.current)
        return None

    @property
    def condition_icon(self) -> int:
        """Return the weather condition icon"""
        if self._weather_data.current is not None:
            return self._weather_data.current.get("icon")
        return None

    @property
    def forecast(self):
        """Return the forecast array."""
        if self._weather_data.forecast is not None:
            fcdata_out = []
            fc_array = self._weather_data.forecast.get("parts", [])
            for data_in in fc_array:
                data_out = {}

                if list(fc_array).index(data_in) == 0:
                    data_out[ATTR_FORECAST_TIME] = dt_util.utcnow() + timedelta(
                        minutes=350
                    )
                if list(fc_array).index(data_in) == 1:
                    data_out[ATTR_FORECAST_TIME] = dt_util.utcnow() + timedelta(
                        minutes=700
                    )

                data_out[ATTR_FORECAST_NATIVE_TEMP] = data_in.get("temp_max")
                data_out[ATTR_FORECAST_NATIVE_TEMP_LOW] = data_in.get("temp_min")
                data_out[ATTR_FORECAST_CONDITION] = get_condition(data_in)

                data_out[ATTR_WEATHER_ICON] = data_in.get("icon")
                data_out[ATTR_FEELS_LIKE_TEMP] = data_in.get("feels_like")
                data_out[ATTR_PRECIPITATION_PROB] = data_in.get("prec_prob")

                data_out[ATTR_FORECAST_NATIVE_WIND_SPEED] = data_in.get("wind_speed")
                data_out[ATTR_FORECAST_WIND_BEARING] = data_in.get("wind_dir")
                data_out[ATTR_FORECAST_NATIVE_PRECIPITATION] = data_in.get("prec_mm")
                data_out[ATTR_FORECAST_NATIVE_PRESSURE] = data_in.get("pressure_pa")
                data_out[ATTR_WEATHER_HUMIDITY] = data_in.get("humidity")

                data_out["part_of_day"] = data_in.get("part_name")
                fcdata_out.append(data_out)

            return fcdata_out

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._weather_data.current is not None

    @property
    def device_state_attributes(self):
        """Return device specific state attributes."""
        if self._weather_data.current is not None:
            data = dict()
            data[ATTR_FEELS_LIKE_TEMP] = self._weather_data.current.get("feels_like")
            data[ATTR_WEATHER_ICON] = self._weather_data.current.get("icon")
            data[ATTR_OBSERVATION_TIME] = dt_util.as_local(
                dt_util.utc_from_timestamp(self._weather_data.current.get("obs_time"))
            ).strftime(TIME_STR_FORMAT)
            return data

        return None


class YandexWeatherApi(object):
    """A class for returning Yandex Weather data."""

    def __init__(self, lat: str, lon: str, api_key, session="none"):
        """Initialize the class."""
        self._api = api_key
        self._lat = lat
        self._lon = lon
        self._session = session

        self._current = None
        self._forecast = None

    async def get_weather(self):
        base_url = f"https://api.weather.yandex.ru/v2/informers?lat={self._lat}&lon={self._lon}"
        headers = {"X-Yandex-API-Key": self._api}

        try:
            async with async_timeout.timeout(5):
                response = await self._session.get(base_url, headers=headers)

            data = await response.json()

            if "status" not in data:
                self._current = data["fact"] if "fact" in data else None
                self._forecast = data["forecast"] if "forecast" in data else None
                _LOGGER.debug(f"Current data:{self._current}")
                _LOGGER.debug(f"Forecast data:{self._forecast}")
            else:
                _LOGGER.error(
                    "Error fetching data from Yandex.Weather, %s, %s",
                    data["status"],
                    data["message"],
                )

        except (asyncio.TimeoutError, aiohttp.ClientError, socket.gaierror) as error:
            _LOGGER.error("Error fetching data from Yandex.Weather, %s", error)

    @property
    def forecast(self):
        """Return forecast"""
        return self._forecast

    @property
    def current(self):
        """Return curent condition"""
        return self._current
