"""
tests/test_weather.py
=====================
Tests unitaires pour tools/weather.py
"""

import pytest
from tools.weather import Weather, WeatherError, WEATHER_CODES


@pytest.fixture
def weather():
    return Weather()


# ─────────────────────────────────────────────
# Tests unitaires (pas besoin d'internet)
# ─────────────────────────────────────────────

def test_weather_codes_not_empty():
    """Les codes météo doivent être définis."""
    assert len(WEATHER_CODES) > 0


def test_weather_code_clear_sky():
    """Code 0 doit être ciel dégagé."""
    assert WEATHER_CODES[0] == "Ciel dégagé"


def test_weather_code_rain():
    """Code 61 doit être pluie légère."""
    assert WEATHER_CODES[61] == "Pluie légère"


def test_weather_can_be_created(weather):
    """Weather doit pouvoir être instancié."""
    assert weather is not None


def test_format_output(weather):
    """_format() doit retourner une string avec la ville."""
    data = {
        "current": {
            "temperature_2m": 20,
            "apparent_temperature": 18,
            "relative_humidity_2m": 65,
            "wind_speed_10m": 15,
            "weather_code": 0,
            "precipitation": 0,
        }
    }
    result = weather._format(data, "Paris", "France")
    assert "Paris" in result
    assert "20" in result
    assert "Ciel dégagé" in result


def test_format_with_precipitation(weather):
    """_format() doit mentionner les précipitations si > 0."""
    data = {
        "current": {
            "temperature_2m": 12,
            "apparent_temperature": 10,
            "relative_humidity_2m": 80,
            "wind_speed_10m": 20,
            "weather_code": 61,
            "precipitation": 2.5,
        }
    }
    result = weather._format(data, "Lyon", "France")
    assert "2.5" in result


def test_format_without_country(weather):
    """_format() doit fonctionner sans pays."""
    data = {
        "current": {
            "temperature_2m": 25,
            "apparent_temperature": 23,
            "relative_humidity_2m": 50,
            "wind_speed_10m": 10,
            "weather_code": 1,
            "precipitation": 0,
        }
    }
    result = weather._format(data, "Montréal", "")
    assert "Montréal" in result


# ─────────────────────────────────────────────
# Tests d'intégration (nécessitent internet)
# ─────────────────────────────────────────────

@pytest.mark.integration
def test_get_weather_by_city(weather):
    """get() avec une ville doit retourner la météo."""
    result = weather.get("Paris")
    assert "Paris" in result
    assert "°C" in result


@pytest.mark.integration
def test_get_weather_montreal(weather):
    """get() pour Montréal doit fonctionner."""
    result = weather.get("Montréal")
    assert "°C" in result


@pytest.mark.integration
def test_get_weather_unknown_city(weather):
    """get() avec une ville inconnue doit lever WeatherError."""
    with pytest.raises(WeatherError):
        weather.get("VilleQuiNExistePas12345")
