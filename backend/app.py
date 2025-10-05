from flask import Flask, render_template, request
from flask_cors import CORS
import requests
from datetime import datetime, timedelta, date as dt

app = Flask(__name__, template_folder='../frontend')
CORS(app)


def parse_num(v):
    """Convert to float safely, remove sentinel values like -999."""
    try:
        n = float(v)
    except Exception:
        return None
    if n <= -900 or abs(n) > 1e6:
        return None
    return n


def safe_get_param(params, key):
    """Get single NASA POWER parameter value safely."""
    if not params or key not in params:
        return None
    val = list(params[key].values())[0]
    return parse_num(val)


@app.route('/frontend/index.html')
def home():
    return render_template('index.html')


@app.route('/frontend/result.html', methods=['POST'])
def weather():
    location = request.form.get('location', '').strip()
    date_str = request.form.get('date', '').strip()
    if not location or not date_str:
        return render_template('result.html',
                               location=location or "—",
                               date=date_str or "—",
                               condition="Missing input ❌",
                               temp_c="N/A", temp_f="N/A",
                               precipitation="N/A",
                               humidity="N/A", wind="N/A",
                               source="N/A")

    today = dt.today()
    try:
        req_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        return render_template('result.html',
                               location=location, date=date_str,
                               condition="Invalid date format ❌",
                               temp_c="N/A", temp_f="N/A",
                               precipitation="N/A",
                               humidity="N/A", wind="N/A",
                               source="N/A")

    # Step 1: Get coordinates
    geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={location}"
    geo_response = requests.get(geo_url)
    geo_data = geo_response.json()
    if not geo_data.get("results"):
        return render_template('result.html',
                               location=location, date=date_str,
                               condition="Location not found ❌",
                               temp_c="N/A", temp_f="N/A",
                               precipitation="N/A",
                               humidity="N/A", wind="N/A",
                               source="Geocoding")

    lat = geo_data["results"][0]["latitude"]
    lon = geo_data["results"][0]["longitude"]

    temp_avg = temp_max = temp_min = precipitation = wind = humidity = None
    source = "Unknown"

    # Step 2: NASA for past (strictly before today), Open-Meteo for today or future
    if req_date < (today - timedelta(days=2)):
        year, month, day = date_str.split('-')
        start = end = f"{year}{month}{day}"

        nasa_url = (
            f"https://power.larc.nasa.gov/api/temporal/daily/point"
            f"?parameters=T2M,T2M_MAX,T2M_MIN,PRECTOTCORR,WS2M,RH2M"
            f"&community=RE"
            f"&longitude={lon}&latitude={lat}"
            f"&start={start}&end={end}&format=JSON"
        )
        nasa_response = requests.get(nasa_url)
        nasa_data = nasa_response.json()

        params = nasa_data.get("properties", {}).get("parameter", {})

        temp_avg = safe_get_param(params, "T2M")
        temp_max = safe_get_param(params, "T2M_MAX")
        temp_min = safe_get_param(params, "T2M_MIN")
        precipitation = safe_get_param(params, "PRECTOTCORR")
        wind = safe_get_param(params, "WS2M")
        humidity = safe_get_param(params, "RH2M")

        if not any([temp_avg, temp_max, temp_min, precipitation, wind, humidity]):
            # fallback if NASA returned empty
            return render_template('result.html',
                                   location=location, date=date_str,
                                   condition="No past weather data found 🛰️",
                                   temp_c="N/A", temp_f="N/A",
                                   precipitation="N/A",
                                   humidity="N/A", wind="N/A",
                                   source="NASA POWER")

        if temp_avg is None and temp_min and temp_max:
            temp_avg = (temp_min + temp_max) / 2

        source = "NASA POWER (Historical)"
    else:
        # --- Open-Meteo for today/future ---
        weather_url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,"
            f"windspeed_10m_max,relative_humidity_2m_max"
            f"&timezone=auto&start_date={date_str}&end_date={date_str}"
        )
        weather_response = requests.get(weather_url)
        weather_data = weather_response.json()

        if "daily" not in weather_data:
            return render_template('result.html',
                                   location=location, date=date_str,
                                   condition="Weather data not available 🛰️",
                                   temp_c="N/A", temp_f="N/A",
                                   precipitation="N/A",
                                   humidity="N/A", wind="N/A",
                                   source="Open-Meteo")

        daily = weather_data["daily"]
        temp_max = parse_num(daily["temperature_2m_max"][0])
        temp_min = parse_num(daily["temperature_2m_min"][0])
        precipitation = parse_num(daily["precipitation_sum"][0])
        wind = parse_num(daily["windspeed_10m_max"][0])
        humidity = parse_num(daily["relative_humidity_2m_max"][0])
        temp_avg = (temp_max + temp_min) / 2 if temp_max and temp_min else temp_max or temp_min

        source = "Open-Meteo (Forecast)"

    # Step 3: Interpret
    if precipitation and precipitation > 5:
        condition = f"very wet ☔ ({precipitation:.1f} mm)"
    elif temp_max and temp_max > 32:
        condition = "very hot 🥵"
    elif temp_min and temp_min < 0:
        condition = "very cold 🧊"
    elif wind and wind > 10:
        condition = "very windy 🌬️"
    elif humidity and humidity > 80:
        condition = "very humid 💧"
    else:
        condition = "comfortable 🌤️"

    temp_f = (temp_avg * 9 / 5 + 32) if temp_avg is not None else None

    return render_template(
        'result.html',
        location=location,
        date=date_str,
        condition=condition,
        temp_c=f"{temp_avg:.1f}" if temp_avg is not None else "N/A",
        temp_f=f"{temp_f:.1f}" if temp_f is not None else "N/A",
        precipitation=f"{precipitation:.1f}" if precipitation is not None else "N/A",
        humidity=f"{humidity:.0f}" if humidity is not None else "N/A",
        wind=f"{wind:.1f}" if wind is not None else "N/A",
        source=source
    )


if __name__ == '__main__':
    app.run(debug=True)
