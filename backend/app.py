from flask import Flask, render_template, request
from flask_cors import CORS
import requests
from datetime import date as dt

app = Flask(__name__, template_folder='../frontend')
CORS(app)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/weather', methods=['POST'])
def weather():
    location = request.form['location']
    date_str = request.form['date']
    today = dt.today().isoformat()

    # Step 1: Get coordinates for the location
    geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={location}"
    geo_response = requests.get(geo_url)
    geo_data = geo_response.json()

    if not geo_data.get("results"):
        return render_template('result.html', location=location, date=date_str,
                               condition="Location not found ❌")

    lat = geo_data["results"][0]["latitude"]
    lon = geo_data["results"][0]["longitude"]

    # Step 2: Choose source — NASA (past) or Open-Meteo (future)
    if date_str <= today:
        # -------- NASA POWER (past data) --------
        year, month, day = date_str.split('-')
        start = end = f"{year}{month}{day}"

        nasa_url = (
            f"https://power.larc.nasa.gov/api/temporal/daily/point"
            f"?parameters=T2M,T2M_MAX,T2M_MIN,PRECTOTCORR"
            f"&community=RE"
            f"&longitude={lon}&latitude={lat}"
            f"&start={start}&end={end}&format=JSON"
        )
        nasa_response = requests.get(nasa_url)
        nasa_data = nasa_response.json()

        if "properties" not in nasa_data or "parameter" not in nasa_data["properties"]:
            return render_template('result.html', location=location, date=date_str,
                                   condition="Weather data not available 🛰️")

        params = nasa_data["properties"]["parameter"]
        temp_avg = list(params["T2M"].values())[0]
        temp_max = list(params["T2M_MAX"].values())[0]
        temp_min = list(params["T2M_MIN"].values())[0]
        precipitation = list(params["PRECTOTCORR"].values())[0]

        source = "NASA POWER (Historical)"

    else:
        # -------- Open-Meteo (future forecast) --------
        weather_url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&daily=temperature_2m_max,temperature_2m_min,precipitation_sum"
            f"&timezone=auto&start_date={date_str}&end_date={date_str}"
        )
        weather_response = requests.get(weather_url)
        weather_data = weather_response.json()

        if "daily" not in weather_data:
            return render_template('result.html', location=location, date=date_str,
                                   condition="Weather data not available 🛰️")

        daily = weather_data["daily"]
        temp_max = daily["temperature_2m_max"][0]
        temp_min = daily["temperature_2m_min"][0]
        precipitation = daily["precipitation_sum"][0]
        temp_avg = (temp_max + temp_min) / 2
        source = "Open-Meteo (Forecast)"

    # Step 3: Interpret data
    if precipitation > 5:
        condition = f"likely rainy ☔ ({precipitation:.1f} mm)"
    elif temp_max > 32:
        condition = f"very hot 🥵 (max {temp_max:.1f}°C)"
    elif temp_min < 0:
        condition = f"very cold 🧊 (min {temp_min:.1f}°C)"
    else:
        condition = f"comfortable 🌤️ ({temp_min:.1f}°C–{temp_max:.1f}°C, low rain)"

    return render_template('result.html',
                           location=location,
                           date=date_str,
                           condition=condition,
                           source=source)

if __name__ == '__main__':
    app.run(debug=True)
