"""
tools/weather.py
================
Météo en temps réel pour Jarvis.

APIs utilisées (toutes gratuites, sans clé) :
- ip-api.com      : géolocalisation par IP
- open-meteo.com  : données météo

Pourquoi pas OpenWeatherMap ?
Nécessite une clé API. On évite les dépendances
aux clés pour les fonctionnalités de base.
"""

import json
import urllib.parse
import urllib.request


# Codes météo WMO → description française
WEATHER_CODES = {
    0: "Ciel dégagé",
    1: "Principalement dégagé",
    2: "Partiellement nuageux",
    3: "Couvert",
    45: "Brouillard",
    48: "Brouillard givrant",
    51: "Bruine légère",
    53: "Bruine modérée",
    55: "Bruine dense",
    61: "Pluie légère",
    63: "Pluie modérée",
    65: "Pluie forte",
    71: "Neige légère",
    73: "Neige modérée",
    75: "Neige forte",
    80: "Averses légères",
    81: "Averses modérées",
    82: "Averses violentes",
    95: "Orage",
    99: "Orage avec grêle",
}


class WeatherError(Exception):
    """Erreur spécifique à la météo."""
    pass


class Weather:
    """
    Récupère la météo en temps réel.

    Usage :
        weather = Weather()
        result = weather.get()
        print(result)
    """

    GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
    WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
    IP_API_URL = "http://ip-api.com/json/"

    def get(self, city: str = None) -> str:
        """
        Retourne la météo actuelle.

        Args:
            city : Ville spécifique (optionnel).
                   Si None, utilise la localisation par IP.

        Returns:
            Météo formatée en string

        Raises:
            WeatherError : Si impossible de récupérer la météo
        """
        if city:
            lat, lon, city_name, country = self._geocode(city)
        else:
            lat, lon, city_name, country = self._locate_by_ip()

        data = self._fetch_weather(lat, lon)
        return self._format(data, city_name, country)

    def _locate_by_ip(self) -> tuple:
        """
        Détermine la localisation via l'adresse IP.

        Returns:
            (latitude, longitude, ville, pays)
        """
        try:
            req = urllib.request.Request(
                self.IP_API_URL,
                headers={"User-Agent": "Jarvis/1.0"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            if data.get("status") != "success":
                raise WeatherError("Géolocalisation échouée.")

            return (
                data["lat"],
                data["lon"],
                data["city"],
                data["country"]
            )
        except WeatherError:
            raise
        except Exception as e:
            raise WeatherError(
                f"Impossible de déterminer la localisation : {e}")

    def _geocode(self, city: str) -> tuple:
        """
        Convertit un nom de ville en coordonnées GPS.

        Returns:
            (latitude, longitude, ville, pays)
        """
        try:
            params = urllib.parse.urlencode({
                "name": city,
                "count": 1,
                "language": "fr"
            })
            url = f"{self.GEOCODING_URL}?{params}"
            with urllib.request.urlopen(url, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            results = data.get("results", [])
            if not results:
                raise WeatherError(f"Ville introuvable : '{city}'")

            r = results[0]
            return (
                r["latitude"],
                r["longitude"],
                r.get("name", city),
                r.get("country", "")
            )
        except WeatherError:
            raise
        except Exception as e:
            raise WeatherError(f"Erreur de géocodage : {e}")

    def _fetch_weather(self, lat: float, lon: float) -> dict:
        """
        Récupère les données météo depuis Open-Meteo.

        Args:
            lat : Latitude
            lon : Longitude

        Returns:
            Données météo brutes
        """
        try:
            params = urllib.parse.urlencode({
                "latitude": lat,
                "longitude": lon,
                "current": ",".join([
                    "temperature_2m",
                    "relative_humidity_2m",
                    "apparent_temperature",
                    "weather_code",
                    "wind_speed_10m",
                    "precipitation",
                ]),
                "wind_speed_unit": "kmh",
                "timezone": "auto"
            })
            url = f"{self.WEATHER_URL}?{params}"
            with urllib.request.urlopen(url, timeout=8) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            raise WeatherError(f"Impossible de récupérer la météo : {e}")

    def _format(self, data: dict, city: str, country: str) -> str:
        """Formate les données météo pour l'affichage."""
        current = data.get("current", {})

        temp = current.get("temperature_2m", "?")
        feels = current.get("apparent_temperature", "?")
        humidity = current.get("relative_humidity_2m", "?")
        wind = current.get("wind_speed_10m", "?")
        code = current.get("weather_code", 0)
        precip = current.get("precipitation", 0)

        description = WEATHER_CODES.get(code, "Conditions inconnues")
        location = f"{city}, {country}" if country else city

        lines = [
            f"Météo à {location} :",
            f"  {description}",
            f"  Température : {temp}°C (ressenti {feels}°C)",
            f"  Humidité    : {humidity}%",
            f"  Vent        : {wind} km/h",
        ]

        if precip and float(precip) > 0:
            lines.append(f"  Précipitations : {precip} mm")

        return "\n".join(lines)
