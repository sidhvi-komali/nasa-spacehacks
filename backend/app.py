from flask import Flask, render_template, request
from flask_cors import CORS
from sklearn.linear_model import LinearRegression
import numpy as np
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


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/weather', methods=['POST'])
def weather():
    location = request.form.get('location', '').strip()
    date_str = request.form.get('date', '').strip()

    if not location or not date_str:
        return render_template(
            'result.html',
            location=location or "—",
            date=date_str or "—",
            condition="Missing input ❌",
            temp_c="N/A", temp_f="N/A",
            precipitation="N/A",
            humidity="N/A", wind="N/A",
            source="N/A"
        )

    today = dt.today()
    try:
        req_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        return render_template(
            'result.html',
            location=location, date=date_str,
            condition="Invalid date format ❌",
            temp_c="N/A", temp_f="N/A",
            precipitation="N/A",
            humidity="N/A", wind="N/A",
            source="N/A"
        )

    # Step 1: Get coordinates
    geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={location}"
    geo_response = requests.get(geo_url)
    geo_data = geo_response.json()

    if not geo_data.get("results"):
        return render_template(
            'result.html',
            location=location, date=date_str,
            condition="Location not found ❌",
            temp_c="N/A", temp_f="N/A",
            precipitation="N/A",
            humidity="N/A", wind="N/A",
            source="Geocoding"
        )

    lat = geo_data["results"][0]["latitude"]
    lon = geo_data["results"][0]["longitude"]

    temp_avg = temp_max = temp_min = precipitation = wind = humidity = None
    source = "Unknown"
    delta_days = (req_date - today).days

    # Step 2: NASA for past (strictly before today - 2 days)
    if req_date < (today - timedelta(days=2)):
        # TODO: Add NASA past-weather handling if needed
        condition = "Historical data not implemented yet 🛰️"
        source = "NASA (Past Data)"

    # Step 3: Open-Meteo for 0–16 days ahead
    elif 0 <= delta_days <= 16:
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
            return render_template(
                'result.html',
                location=location, date=date_str,
                condition="Weather data not available 🛰️",
                temp_c="N/A", temp_f="N/A",
                precipitation="N/A",
                humidity="N/A", wind="N/A",
                source="Open-Meteo"
            )

        daily = weather_data["daily"]
        temp_max = parse_num(daily["temperature_2m_max"][0])
        temp_min = parse_num(daily["temperature_2m_min"][0])
        precipitation = parse_num(daily["precipitation_sum"][0])
        wind = parse_num(daily["windspeed_10m_max"][0])
        humidity = parse_num(daily["relative_humidity_2m_max"][0])

        temp_avg = (temp_max + temp_min) / 2 if temp_max and temp_min else temp_max or temp_min
        source = "Open-Meteo (Forecast)"

    # Step 4: Predict beyond 16 days
    else:
        end_date = today - timedelta(days=1)
        start_date = end_date - timedelta(days=30)
        start_str = start_date.strftime("%Y%m%d")
        end_str = end_date.strftime("%Y%m%d")

        nasa_url = (
            f"https://power.larc.nasa.gov/api/temporal/daily/point"
            f"?parameters=T2M_MAX,T2M_MIN,PRECTOTCORR"
            f"&community=RE&longitude={lon}&latitude={lat}"
            f"&start={start_str}&end={end_str}&format=JSON"
        )
        nasa_response = requests.get(nasa_url)
        nasa_data = nasa_response.json()
        params = nasa_data.get("properties", {}).get("parameter", {})

        if not params:
            return render_template(
                'result.html',
                location=location, date=date_str,
                condition="No data to predict future weather 🛰️",
                temp_c="N/A", temp_f="N/A",
                precipitation="N/A",
                humidity="N/A", wind="N/A",
                source="Trend Prediction"
            )

        days = np.arange(1, len(params["T2M_MAX"]) + 1).reshape(-1, 1)
        tmax = np.array(list(params["T2M_MAX"].values()))
        tmin = np.array(list(params["T2M_MIN"].values()))
        precip = np.array(list(params["PRECTOTCORR"].values()))

        mask = (tmax > -900) & (tmin > -900)
        days, tmax, tmin, precip = days[mask], tmax[mask], tmin[mask], precip[mask]

        model_tmax = LinearRegression().fit(days, tmax)
        model_tmin = LinearRegression().fit(days, tmin)
        model_precip = LinearRegression().fit(days, precip)

        future_day = len(days) + delta_days
        temp_max = float(model_tmax.predict([[future_day]])[0])
        temp_min = float(model_tmin.predict([[future_day]])[0])
        precipitation = max(0, float(model_precip.predict([[future_day]])[0]))
        temp_avg = (temp_max + temp_min) / 2
        source = "Predicted via NASA Trend Model"

    # Step 5: Interpret condition
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
        source=source,
        lat=lat,
        lon=lon
    )



if __name__ == '__main__':
    app.run(debug=True)
