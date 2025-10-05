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

    # Get Coordinates From Location
    geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={location}"
    geo_response = requests.get(geo_url)
    geo_data = geo_response.json()

    if not geo_data.get("results"):
        return render_template('result.html', location=location, date=date,
                               condition="Location not found ❌")

    lat = geo_data["results"][0]["latitude"]
    lon = geo_data["results"][0]["longitude"]

    # Format date for NASA POWER API (YYYYMMDD)
    year, month, day = date.split('-')
    start = end = f"{year}{month}{day}"
    

    # NASA POWER API URL
    nasa_url = (
        f"https://power.larc.nasa.gov/api/temporal/daily/point"
        f"?parameters=T2M,T2M_MAX,T2M_MIN,PRECTOTCORR"
        f"&community=RE"
        f"&longitude={lon}"
        f"&latitude={lat}"
        f"&start={start}"
        f"&end={end}"
        f"&format=JSON"
    )

    nasa_response = requests.get(nasa_url)
    nasa_data = nasa_response.json()

    if "properties" not in nasa_data or "parameter" not in nasa_data["properties"]:
        return render_template('result.html', location=location, date=date,
                               condition="Weather data not available 🛰️")

    params = nasa_data["properties"]["parameter"]

    temp_avg = list(params["T2M"].values())[0]
    temp_max = list(params["T2M_MAX"].values())[0]
    temp_min = list(params["T2M_MIN"].values())[0]
    precipitation = list(params["PRECTOTCORR"].values())[0]

    # Step 3: Interpret the data
    if precipitation > 5:
        condition = f"likely rainy ☔ (avg {precipitation:.1f} mm of rain)"
    elif temp_max > 32:
        condition = f"very hot 🥵 (max {temp_max:.1f}°C)"
    elif temp_min < 0:
        condition = f"very cold 🧊 (min {temp_min:.1f}°C)"
    else:
        condition = f"comfortable 🌤️ (avg {temp_avg:.1f}°C, low rain)"

    return render_template('result.html',
                           location=location,
                           date=date,
                           condition=condition)

if __name__ == '__main__':
    app.run(debug=True)


'''
If yo’re planning an outdoor event—like a vacation, a hike on a trail, 
or fishing on a lake—it would be good to know the chances of adverse weather 
for the time and location you are considering. There are many types of Earth
observation data that can provide information on weather conditions for a 
particular location and day of the year. Your challenge is to construct an 
app with a personalized interface that enables users to conduct a customized
query to tell them the likelihood of “very hot,” “very cold,” “very windy,”
“very wet,” or “very uncomfortable” conditions for the location and time 
they specify. (Earth Science Division)
'''
