from flask import Flask, render_template, request
import requests
from datetime import datetime, timedelta, date as dt
import numpy as np
from sklearn.linear_model import LinearRegression

# Set the template folder relative to the current directory
app = Flask(__name__, template_folder='../frontend')

# ---------------------------
# Helpers
# ---------------------------
def parse_num(v):
    """Safely converts a value to a float, returning None for invalid numbers or placeholders."""
    try:
        n = float(v)
        # NASA's API uses -999 or similar for missing data
        if n <= -900 or abs(n) > 1e6:
            return None
        return n
    except Exception:
        return None

def get_coords(city, state, country):
    """
    Looks up geographic coordinates for a given city, state, and country.
    
    Includes normalization for US addresses to improve geocoding reliability
    (e.g., uses 'USA' and uppercase state abbreviations).
    """
    city = city.strip()
    state = state.strip()
    country = country.strip()
    
    # Normalize country and state format for geocoding API
    country_lower = country.lower()
    if country_lower in ["united states", "usa", "u.s.a.", "us"]:
        country_part = "USA"
        state_part = state.upper() # Use uppercase for US state abbreviations (CA, NY, etc.)
    else:
        country_part = country.title()
        state_part = state.title()
        
    query = f"{city.title()}, {state_part}, {country_part}"
    
    # Use the Open-Meteo Geocoding API
    geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={query}"
    
    # Simple retry mechanism for fetch
    for attempt in range(3):
        try:
            resp = requests.get(geo_url, timeout=5).json()
            break
        except requests.exceptions.RequestException as e:
            print(f"Geocoding request failed on attempt {attempt+1}: {e}")
            if attempt == 2:
                return None, None # Give up after 3 attempts

    print("Geocoding response:", resp)
    results = resp.get("results")
    
    if results and len(results) > 0:
        # Return the coordinates of the first result
        return float(results[0]["latitude"]), float(results[0]["longitude"])
        
    # If the combined query fails, try just the city name as a fallback
    print(f"Full query '{query}' failed. Trying fallback: '{city}'")
    fallback_query = city.title()
    geo_url_fallback = f"https://geocoding-api.open-meteo.com/v1/search?name={fallback_query}"
    
    try:
        resp_fallback = requests.get(geo_url_fallback, timeout=5).json()
        results_fallback = resp_fallback.get("results")
        if results_fallback:
             # Find the best match by checking the country/admin_area
            for result in results_fallback:
                # Check for country match (or USA/US variants)
                country_match = False
                if country_part == "USA" and result.get("country_code") == "US":
                    country_match = True
                elif result.get("country_code", "").lower() == country_part.lower():
                    country_match = True

                # For US locations, check the administrative area (state)
                if country_part == "USA":
                    admin_area = result.get("admin1", "")
                    if admin_area.upper() == state_part:
                         return float(result["latitude"]), float(result["longitude"])
                
                # For non-US, just use the first result if the country matches
                elif country_match:
                    return float(result["latitude"]), float(result["longitude"])

            # If no perfect match found, use the first general result
            if results_fallback:
                return float(results_fallback[0]["latitude"]), float(results_fallback[0]["longitude"])

    except requests.exceptions.RequestException as e:
        print(f"Fallback geocoding request failed: {e}")

    return None, None

# ---------------------------
# Routes
# ---------------------------
@app.route('/')
def home():
    today = dt.today()
    max_date = (today + timedelta(days=365*5)).strftime("%Y-%m-%d")
    min_date = (today - timedelta(days=365*20)).strftime("%Y-%m-%d")
    return render_template('index.html', min_date=min_date, max_date=max_date)

@app.route('/weather', methods=['POST'])
def weather():
    city = request.form.get('city', '').strip()
    state = request.form.get('state', '').strip()
    country = request.form.get('country', '').strip()
    date_str = request.form.get('date', '').strip()

    if not city or not state or not country or not date_str:
        return render_template(
            'result.html',
            location="—",
            date=date_str or "—",
            condition="Missing input ❌",
            temp_c="N/A",
            temp_f="N/A",
            precipitation="N/A",
            humidity="N/A",
            wind="N/A",
            source="N/A"
        )

    today = dt.today()
    try:
        req_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        return render_template(
            'result.html',
            location=f"{city}, {state}, {country}",
            date=date_str,
            condition="Invalid date format ❌",
            temp_c="N/A",
            temp_f="N/A",
            precipitation="N/A",
            humidity="N/A",
            wind="N/A",
            source="N/A"
        )

    lat, lon = get_coords(city, state, country)
    if lat is None or lon is None:
        return render_template(
            'result.html',
            location=f"{city}, {state}, {country}",
            date=date_str,
            condition="Location not found ❌",
            temp_c="N/A",
            temp_f="N/A",
            precipitation="N/A",
            humidity="N/A",
            wind="N/A",
            source="Geocoding"
        )

    temp_max = temp_min = temp_avg = precipitation = humidity = wind = None
    source = "Unknown"

    delta_days = (req_date - today).days

    # ---------------------------
    # Past data from NASA (today - 2 and earlier)
    # ---------------------------
    if delta_days <= -2:
        start_str = req_date.strftime("%Y%m%d")
        nasa_url = (
            f"https://power.larc.nasa.gov/api/temporal/daily/point"
            f"?parameters=T2M_MAX,T2M_MIN,PRECTOTCORR,WS10M,RH2M"
            f"&community=RE&longitude={lon}&latitude={lat}"
            f"&start={start_str}&end={start_str}&format=JSON"
        )
        nasa_data = requests.get(nasa_url).json()
        params = nasa_data.get("properties", {}).get("parameter", {})

        tmax = list(params.get("T2M_MAX", {}).values())
        tmin = list(params.get("T2M_MIN", {}).values())
        precip = list(params.get("PRECTOTCORR", {}).values())
        wind_list = list(params.get("WS10M", {}).values())
        hum_list = list(params.get("RH2M", {}).values())

        if tmax and tmin:
            temp_max = parse_num(tmax[0])
            temp_min = parse_num(tmin[0])
            temp_avg = (temp_max + temp_min) / 2
        if precip:
            precipitation = parse_num(precip[0])
        if wind_list:
            wind = parse_num(wind_list[0])
        if hum_list:
            humidity = parse_num(hum_list[0])
        source = "NASA (Past Data)"

    # ---------------------------
    # Near future (today -1 to today +16)
    # ---------------------------
    elif -1 <= delta_days <= 16:
        weather_url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,"
            f"windspeed_10m_max,relative_humidity_2m_max"
            f"&timezone=auto&start_date={date_str}&end_date={date_str}"
        )
        weather_data = requests.get(weather_url).json()
        daily = weather_data.get("daily", {})

        if daily:
            temp_max = parse_num(daily["temperature_2m_max"][0])
            temp_min = parse_num(daily["temperature_2m_min"][0])
            temp_avg = (temp_max + temp_min) / 2
            precipitation = parse_num(daily["precipitation_sum"][0])
            wind = parse_num(daily["windspeed_10m_max"][0])
            humidity = parse_num(daily["relative_humidity_2m_max"][0])
            source = "Open-Meteo Forecast"

    # ---------------------------
    # Far future (> today +16) using linear regression on recent NASA data
    # ---------------------------
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
        nasa_data = requests.get(nasa_url).json()
        params = nasa_data.get("properties", {}).get("parameter", {})

        if params:
            # Prepare data for regression
            tmax_data = list(params.get("T2M_MAX", {}).values())
            tmin_data = list(params.get("T2M_MIN", {}).values())
            precip_data = list(params.get("PRECTOTCORR", {}).values())
            
            # Ensure all lists are the same length
            min_len = min(len(tmax_data), len(tmin_data), len(precip_data))
            
            days_arr = np.arange(1, min_len + 1).reshape(-1, 1)
            tmax_arr = np.array(tmax_data[:min_len])
            tmin_arr = np.array(tmin_data[:min_len])
            precip_arr = np.array(precip_data[:min_len])
            
            # Filter out missing values (NASA uses -999 for missing data)
            mask = (tmax_arr > -900) & (tmin_arr > -900)
            days_arr, tmax_arr, tmin_arr, precip_arr = days_arr[mask], tmax_arr[mask], tmin_arr[mask], precip_arr[mask]

            if len(days_arr) >= 2: # Need at least 2 data points for linear regression
                # Train models
                model_tmax = LinearRegression().fit(days_arr, tmax_arr)
                model_tmin = LinearRegression().fit(days_arr, tmin_arr)
                model_precip = LinearRegression().fit(days_arr, precip_arr)

                # Predict future data point
                future_day = len(days_arr) + delta_days
                temp_max = float(model_tmax.predict([[future_day]])[0])
                temp_min = float(model_tmin.predict([[future_day]])[0])
                temp_avg = (temp_max + temp_min) / 2
                precipitation = max(0, float(model_precip.predict([[future_day]])[0]))
                source = "Predicted via NASA Trend Model"
            else:
                source = "NASA Data Insufficient for Prediction"
                # Keep values as None to return N/A
        else:
            source = "NASA Data Not Available"

    # ---------------------------
    # Weather condition
    # ---------------------------
    # Note: Only check condition if we have data
    condition = "Unknown ❓"
    if temp_max is not None:
        if precipitation is not None and precipitation > 5:
            condition = f"Very Wet ☔ ({precipitation:.1f} mm)"
        elif temp_max > 32:
            condition = "Very Hot 🥵"
        elif temp_min is not None and temp_min < 0:
            condition = "Very Cold 🧊"
        elif wind is not None and wind > 10:
            condition = "Very Windy 🌬️"
        elif humidity is not None and humidity > 80:
            condition = "Very Humid 💧"
        else:
            condition = "Comfortable 🌤️"
    
    # Calculate Fahrenheit if Celsius average exists
    temp_f = (temp_avg * 9 / 5 + 32) if temp_avg is not None else None

    return render_template(
        'result.html',
        location=f"{city}, {state}, {country}",
        date=req_date.strftime("%m/%d/%Y"),
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
