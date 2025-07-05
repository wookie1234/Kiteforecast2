import streamlit as st
import requests
from datetime import datetime
import pandas as pd
import matplotlib.pyplot as plt
from bs4 import BeautifulSoup
from PIL import Image
from io import BytesIO

# Forecast Daten Tal (Reschensee)
def get_forecast():
    try:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": 46.836,
            "longitude": 10.508,
            "hourly": "windspeed_10m,winddirection_10m,cloudcover,temperature_2m",
            "forecast_days": 4,
            "timezone": "Europe/Berlin"
        }
        r = requests.get(url)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"Fehler beim Abrufen der Tal-Wetterdaten: {e}")
        return None

# Forecast Daten Berg (Haider Alm)
def get_mountain_temp():
    try:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": 46.8,
            "longitude": 10.55,
            "elevation": 2100,
            "hourly": "temperature_2m",
            "forecast_days": 1,
            "timezone": "Europe/Berlin"
        }
        r = requests.get(url)
        r.raise_for_status()
        return r.json()['hourly']
    except Exception as e:
        st.error(f"Fehler beim Abrufen der Berg-Temperaturdaten: {e}")
        return {"temperature_2m": []}

# Luftdruck abrufen
def get_pressure(city_id):
    try:
        url = f"https://www.wetterkontor.de/de/wetter/{city_id}"
        r = requests.get(url, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        text = soup.find(string=lambda t: "Luftdruck" in t)
        import re
        if text:
            m = re.search(r"(\d{3,4}\.\d)", text)
            if m:
                return float(m.group(1))
    except Exception as e:
        st.warning(f"Fehler beim Abrufen des Luftdrucks für {city_id}: {e}")
    return None

# Webcam-Helligkeit
def check_webcam_visibility():
    try:
        url = "https://www.kiteboarding-reschen.eu/webcam/webcam.jpg"
        img_data = requests.get(url).content
        img = Image.open(BytesIO(img_data)).convert("L")
        brightness = sum(img.getdata()) / (img.width * img.height)
        return brightness > 100
    except Exception as e:
        st.warning(f"Webcam nicht verfügbar: {e}")
        return None

# Streamlit Interface
st.set_page_config(page_title="Kite Forecast Reschensee", layout="centered")
st.title("🏄 Kite Forecast Reschensee")

forecast_data = get_forecast()
mountain_temp_data = get_mountain_temp()
bozen_pressure = get_pressure("stadt.asp?land=IT&id=11560")
innsbruck_pressure = get_pressure("stadt.asp?land=AT&id=11115")
diff_pressure = bozen_pressure - innsbruck_pressure if bozen_pressure and innsbruck_pressure else None
visibility_ok = check_webcam_visibility()

if forecast_data is None:
    st.stop()

# Datenframe aufbauen
df_data = {
    "Date": [], "Hour": [], "Wind Speed": [], "Wind Dir": [],
    "Cloud Cover": [], "Temp": [], "Temp_Mountain": []
}

for i in range(len(forecast_data['hourly']['time'])):
    dt = datetime.fromisoformat(forecast_data['hourly']['time'][i])
    df_data["Date"].append(dt.date())
    df_data["Hour"].append(dt.hour)
    df_data["Wind Speed"].append(forecast_data['hourly']['windspeed_10m'][i])
    df_data["Wind Dir"].append(forecast_data['hourly']['winddirection_10m'][i])
    df_data["Cloud Cover"].append(forecast_data['hourly']['cloudcover'][i])
    df_data["Temp"].append(forecast_data['hourly']['temperature_2m'][i])
    mt = mountain_temp_data['temperature_2m'][i] if i < len(mountain_temp_data['temperature_2m']) else None
    df_data["Temp_Mountain"].append(mt)

forecast_df = pd.DataFrame(df_data)

# Bewertung pro Tag
daily_scores = []
for date, group in forecast_df.groupby("Date"):
    kite_hours = group[(group["Hour"] >= 11) & (group["Hour"] <= 16) &
                       (group["Wind Speed"] >= 6.2) &
                       (group["Wind Dir"] >= 140) & (group["Wind Dir"] <= 220)]
    cloud_morning = group[(group["Hour"] >= 6) & (group["Hour"] <= 10)]["Cloud Cover"].mean()
    temp_tal = group[(group["Hour"] >= 9) & (group["Hour"] <= 10)]["Temp"].mean()
    temp_berg = group[(group["Hour"] >= 9) & (group["Hour"] <= 10)]["Temp_Mountain"].mean()
    delta_temp = temp_tal - temp_berg if temp_tal and temp_berg else None

    score = 0
    if cloud_morning < 30:
        score += 30
    elif cloud_morning < 60:
        score += 10
    else:
        score -= 10

    if diff_pressure is not None:
        if diff_pressure < -6:
            score -= 30
        elif diff_pressure < -4:
            score -= 10
        else:
            score += 10

    if delta_temp and delta_temp >= 6:
        score += 15
    elif delta_temp and delta_temp >= 3:
        score += 5
    else:
        score -= 5

    score += len(kite_hours) * 10

    if score >= 50 and visibility_ok:
        status = "🟢 Go"
    elif score >= 20:
        status = "🟡 Risky"
    else:
        status = "🔴 No Go"

    daily_scores.append({
        "Date": date,
        "CloudAvg6-10": cloud_morning,
        "TempDiff_Berg-Tal": delta_temp,
        "KiteableHours": len(kite_hours),
        "PressureDiff": diff_pressure,
        "WebcamBright": visibility_ok,
        "Score": score,
        "Status": status
    })

# Ergebnis anzeigen
score_df = pd.DataFrame(daily_scores)
st.subheader("📊 Kite Forecast Übersicht")
st.dataframe(score_df)

# Diagramm
fig, ax = plt.subplots(figsize=(10, 4))
ax.bar(score_df['Date'].astype(str), score_df['Score'], color='skyblue')
ax.set_title("Kite Score (Reschensee)")
ax.set_ylabel("Score")
ax.set_xlabel("Datum")
ax.grid(True)
st.pyplot(fig)

# Zusatzinfo
st.markdown(f"**Bozen Druck:** {bozen_pressure} hPa")
st.markdown(f"**Innsbruck Druck:** {innsbruck_pressure} hPa")
st.markdown(f"**Druckdifferenz:** {diff_pressure:.2f} hPa" if diff_pressure else "Keine Druckdifferenz verfügbar")
st.markdown(f"**Webcam Sicht:** {'✅ Klar' if visibility_ok else '❌ Eingetrübt oder Fehler'}")
