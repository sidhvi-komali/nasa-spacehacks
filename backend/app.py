from flask import Flask, render_template, request
from flask_cors import CORS
import requests

app = Flask(__name__, template_folder='../frontend')
CORS(app)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/weather', methods=['POST'])
def weather():
    location = request.form['location']
    date = request.form['date']

    # --- Get Coordinates ---
    geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={location}"
    geo_data = requests.get(geo_url).json()

    if not geo_data.get("results"):
        return render_template('result.html', location=location, date=date,
                                condition="❌ Location not found")

    lat = geo_data["results"][0]["latitude"]
    lon = geo_data["results"][0]["longitude"]

    # --- Format Date (YYYYMMDD) ---
    year, month, day = date.split('-')
    date_fmt = f"{year}{month}{day}"

    # --- Fetch NASA POWER Data ---
    nasa_url = (
        f"https://power.larc.nasa.gov/api/temporal/daily/point?"
        f"parameters=T2M,T2M_MAX,T2M_MIN,PRECTOTCORR&community=RE"
        f"&longitude={lon}&latitude={lat}"
        f"&start={date_fmt}&end={date_fmt}&format=JSON"
    )
    nasa_data = requests.get(nasa_url).json()

    try:
        params = nasa_data["properties"]["parameter"]
        temp_avg = list(params["T2M"].values())[0]
        temp_max = list(params["T2M_MAX"].values())[0]
        temp_min = list(params["T2M_MIN"].values())[0]
        precipitation = list(params["PRECTOTCORR"].values())[0]
    except (KeyError, IndexError):
        return render_template('result.html', location=location, date=date,
                                condition="🛰️ Weather data not available")

    # --- Interpret Conditions ---
    if precipitation > 5:
        condition = f"☔ Likely rainy (avg {precipitation:.1f} mm)"
    elif temp_max > 32:
        condition = f"🥵 Very hot (max {temp_max:.1f}°C)"
    elif temp_min < 0:
        condition = f"🧊 Very cold (min {temp_min:.1f}°C)"
    else:
        condition = f"🌤️ Comfortable (avg {temp_avg:.1f}°C, low rain)"

    return render_template('result.html',
                            location=location,
                            date=date,
                            condition=condition)

if __name__ == '__main__':
    app.run(debug=True)