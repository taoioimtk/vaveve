import base64
import logging
import random
import sys
from typing import Optional, Tuple

import requests
from seleniumbase import SB

# --- Configuration ---
TARGET_B64: str = "YnJ1dGFsbGVz"  # Base64 encoded username
GEO_API_URL: str = "http://ip-api.com/json/"
TWITCH_URL_TEMPLATE: str = "https://www.twitch.tv/{username}"

# Sleep durations (in seconds)
MIN_WATCH_TIME: int = 450
MAX_WATCH_TIME: int = 800
SHORT_SLEEP: int = 2
MEDIUM_SLEEP: int = 10
LOAD_SLEEP: int = 12

# Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

def get_geolocation() -> Optional[Tuple[float, float, str]]:
    """
    Fetches geolocation data from the API.
    Returns: Tuple (latitude, longitude, timezone_id) or None if failed.
    """
    try:
        logger.info("Fetching geolocation data...")
        response = requests.get(GEO_API_URL, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        lat = data.get("lat")
        lon = data.get("lon")
        tz = data.get("timezone")
        
        if lat and lon and tz:
            logger.info(f"Location found: {data.get('city', 'Unknown')}, {data.get('countryCode')} (TZ: {tz})")
            return lat, lon, tz
        else:
            logger.error("Incomplete geolocation data received.")
            return None

    except requests.RequestException as e:
        logger.error(f"Failed to retrieve geolocation: {e}")
        return None

def handle_cookie_consent(driver):
    """Handles common cookie consent popups."""
    consent_buttons = [
        'button:contains("Accept")',
        'button:contains("Start Watching")'
    ]
    
    for selector in consent_buttons:
        if driver.is_element_present(selector):
            try:
                driver.cdp.click(selector, timeout=4)
                logger.info(f"Clicked consent button: {selector}")
                driver.sleep(SHORT_SLEEP)
            except Exception as e:
                logger.warning(f"Found button but failed to click {selector}: {e}")

def run_bot():
    """Main execution loop."""
    
    # Decode the target username
    try:
        target_username = base64.b64decode(TARGET_B64).decode("utf-8")
        target_url = TWITCH_URL_TEMPLATE.format(username=target_username)
        logger.info(f"Target URL: {target_url}")
    except Exception as e:
        logger.critical(f"Failed to decode target string: {e}")
        sys.exit(1)

    # Get Geolocation
    geo_data = get_geolocation()
    if not geo_data:
        sys.exit(1)
        
    latitude, longitude, timezone_id = geo_data
    proxy_str = False  # Set to your proxy string if needed

    logger.info("Starting viewer loop...")

    while True:
        watch_duration = random.randint(MIN_WATCH_TIME, MAX_WATCH_TIME)
        
        # Context manager ensures the driver closes properly
        with SB(
            uc=True, 
            locale="en", 
            ad_block=True, 
            chromium_arg='--disable-webgl', 
            proxy=proxy_str
        ) as driver:
            
            logger.info("Initializing browser session...")
            driver.activate_cdp_mode(
                target_url, 
                tzone=timezone_id, 
                geoloc=(latitude, longitude)
            )
            driver.sleep(SHORT_SLEEP)
            
            # Handle initial popups
            handle_cookie_consent(driver)
            driver.sleep(LOAD_SLEEP)
            
            # Handle potential post-load popups
            handle_cookie_consent(driver)

            # Check if stream information is present
            if driver.is_element_present("#live-channel-stream-information"):
                logger.info("Stream information found. Initializing secondary view...")
                
                # Logic from original script: Open a second driver instance
                secondary_driver = driver.get_new_driver(undetectable=True)
                secondary_driver.activate_cdp_mode(
                    target_url, 
                    tzone=timezone_id, 
                    geoloc=(latitude, longitude)
                )
                secondary_driver.sleep(MEDIUM_SLEEP)
                
                handle_cookie_consent(secondary_driver)
                
                if secondary_driver.is_element_present('button:contains("Start Watching")'):
                    secondary_driver.cdp.click('button:contains("Start Watching")', timeout=4)
                    secondary_driver.sleep(MEDIUM_SLEEP)

                if secondary_driver.is_element_present('button:contains("Accept")'):
                    secondary_driver.cdp.click('button:contains("Accept")', timeout=4)

                # Sleep main thread while "watching"
                logger.info(f"Watching stream for {watch_duration} seconds...")
                driver.sleep(watch_duration)
                
                # Note: secondary_driver is automatically closed when 'driver' context exits or 
                # explicitly managed if needed outside this block.
            else:
                logger.warning("Stream information not found. Exiting loop.")
                break

if __name__ == "__main__":
    run_bot()
