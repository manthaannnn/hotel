import streamlit as st
import asyncio
from playwright.async_api import async_playwright
from datetime import datetime
import os
import json
import urllib.parse
from openai import OpenAI
import threading


client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

adults = 2
children = 0
rooms = 1

# GPT Extraction

def gpt_extract(prompt, label):
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": f"You extract hotel room names and their prices from {label} page text."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        st.error(f"GPT Error ({label}): {e}")
        return ""

def extract_booking_prices(text):
    prompt = f"""
You are a travel assistant. From the following Booking.com page text, extract **room names** and their corresponding **price (in INR)**.

✨ Use only room names that match:
- Super Deluxe Room with Balcony
- Superior Double Room
- Deluxe King Room
- Deluxe Double Room
- Deluxe Family Room
- Two-Bedroom Villa
- Villa with Garden View
- Superior Villa

Format:
Room Name – ₹Price

Only extract ONE price per room. Skip unmatched names.

{text}
"""
    return gpt_extract(prompt, "Booking")

def extract_agoda_prices(text):
    prompt = f"""
You are a travel assistant. From the following Agoda page text, extract **room names** and their corresponding **price (in INR)**.

✨ Use only room names that match:
- Superior Room
- Super Deluxe Room with Balcony
- Super Deluxe Room 
- Deluxe Dbl
- Family Deluxe
- Standard Villa 2 Bedroom
- Standard Villa Garden View
- Villa - 4-Bedroom
- Superior Villa

Format:
Room Name – ₹Price

Only extract ONE price per room. Skip unmatched names.

{text}
"""
    return gpt_extract(prompt, "Agoda")

def extract_goibibo_prices(text):
    prompt = f"""
You are a travel assistant. From the following Goibibo page text, extract **room names** and their corresponding **price (in INR)**.

✨ Use only room names that match:
- Super Delux Balcony Room
- Superior Rooms
- Deluxe Room with Balcony
- Super Deluxe Rooms

Format:
Room Name – ₹Price

Only extract ONE price per room. Skip unmatched names.

{text}
"""
    return gpt_extract(prompt, "Goibibo")

def generate_goibibo_link(checkin, checkout):
    ci = datetime.strptime(checkin, "%Y-%m-%d").strftime("%Y%m%d")
    co = datetime.strptime(checkout, "%Y-%m-%d").strftime("%Y%m%d")
    r = f"{rooms}-{adults}-{children}"
    hquery_dict = {"ci": ci, "co": co, "r": r, "ibp": ""}
    hquery_encoded = urllib.parse.quote(json.dumps(hquery_dict))
    hotel_id = "2259653877757301726"
    mmt_id = "201203212233088600"
    city_code = "CTXOP"
    city_name = "Dwarka"
    return (
        f"https://www.goibibo.com/hotels/goverdhan-greens-hotel-in-dwarka-{hotel_id}/"
        f"?hquery={hquery_encoded}&cc=IN&vcid={hotel_id}&locusId={city_code}&locusType=city"
        f"&cityCode={city_code}&mmtId={mmt_id}&topHtlId={mmt_id}&FS=GSU&city={city_name}&sType=hotel"
    )

async def extract_text_from_sites(urls):
    extracted = {}
    async with async_playwright() as p:
        browser = await p.firefox.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        for site, url in urls.items():
            try:
                await page.goto(url, timeout=90000, wait_until='load')
                await page.wait_for_timeout(5000)
                full_text = await page.evaluate("document.body.innerText")
                extracted[site] = full_text
            except Exception as e:
                st.error(f"Error scraping {site}: {e}")

        await browser.close()
    return extracted

def run_playwright_in_thread(urls):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(extract_text_from_sites(urls))

# Streamlit UI
st.title("🛎️ Hotel Price Extractor")

checkin = st.date_input("Check-in Date", value=datetime(2025, 7, 2)).strftime("%Y-%m-%d")
checkout = st.date_input("Check-out Date", value=datetime(2025, 7, 3)).strftime("%Y-%m-%d")

if st.button("Extract Hotel Prices"):
    urls = {
        "booking": (
            f"https://www.booking.com/hotel/in/goverdhan-greens-resort.en-gb.html?"
            f"checkin={checkin}&checkout={checkout}&group_adults={adults}&group_children={children}&no_rooms={rooms}&selected_currency=INR"
        ),
        "agoda": (
            f"https://www.agoda.com/goverdhan-greens/hotel/baradia-in.html?"
            f"adults={adults}&children={children}&rooms={rooms}&checkIn={checkin}"
            f"&los={(datetime.strptime(checkout, '%Y-%m-%d') - datetime.strptime(checkin, '%Y-%m-%d')).days}&currencyCode=INR"
        ),
        "goibibo": generate_goibibo_link(checkin, checkout),
    }

    with st.spinner("Scraping hotel websites..."):
        text_data = run_playwright_in_thread(urls)

    st.success("Scraping complete. Running GPT extraction...")
    all_data = {}

    for site, text in text_data.items():
        if site == "booking":
            result = extract_booking_prices(text)
        elif site == "agoda":
            result = extract_agoda_prices(text)
        elif site == "goibibo":
            result = extract_goibibo_prices(text)
        else:
            result = ""

        extracted = {}
        for line in result.splitlines():
            if "– ₹" in line:
                try:
                    room, price = line.split("– ₹")
                    extracted[room.strip()] = f"₹{price.strip()}"
                except:
                    pass

        all_data[site] = extracted

    st.header("📊 Extracted Hotel Prices")
    for site in all_data:
        st.subheader(site.capitalize())
        for room, price in all_data[site].items():
            st.write(f"- {room}: {price}")
