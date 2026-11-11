"""
Selenium driver for flatfox.ch.
"""

import re
import time

import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from src.lib.email_client import EmailClient
from src.lib.errors import SendError
from src.search_profile import SearchProfile

TIME_DELAY_ON_LOAD = 0.5


class FlatfoxWebInteractor:
    """
    Log in to flatfox.ch (with an emailed one-time code), search shared flats and
    send contact requests.
    """

    def __init__(self, profile: SearchProfile, email_client: EmailClient) -> None:
        """
        Start a Chrome session.

        :param profile: Profile with the Flatfox login, search and contact details.
        :param email_client: Client used to read the login code from the inbox.
        """
        self.base_url = "https://flatfox.ch/en/accounts/login/?next=/en/search/"
        self.profile = profile
        self.email_client = email_client
        self.driver = webdriver.Chrome()
        self.state = "STARTING"

    def load(self) -> None:
        """
        Open the login page and accept the cookie banner.
        """
        self.driver.get(self.base_url)
        time.sleep(TIME_DELAY_ON_LOAD)
        self.driver.find_element(By.ID, "onetrust-accept-btn-handler").click()
        time.sleep(TIME_DELAY_ON_LOAD)
        self.state = "LOADED"

    def enter(self) -> None:
        """
        Log in with email, password and the one-time code sent by email.

        :raises EmailError: If the login code does not arrive.
        """
        self.driver.find_element(By.ID, "id_email").send_keys(
            self.profile.flatfox_login
        )
        continue_button = self.driver.find_element(By.CLASS_NAME, "css-1iioj0r")
        continue_button.click()
        time.sleep(TIME_DELAY_ON_LOAD)
        self.driver.find_element(By.ID, "id_password").send_keys(
            self.profile.flatfox_password
        )
        continue_button.click()
        code = self.email_client.retrieve_6digit_code(sender="flatfox")
        self.driver.find_element(By.ID, "f1").send_keys(code)
        continue_button.click()
        self.state = "ENTERED"

    def search(self) -> None:
        """
        Search shared flats in the profile's place, up to the maximum rent.
        """
        time.sleep(1)
        region_field = self.driver.find_element(
            By.CLASS_NAME, "mapboxgl-ctrl-geocoder--input"
        )
        region_field.send_keys(self.profile.place)
        time.sleep(1)
        self.driver.find_element(
            By.CLASS_NAME, "mapboxgl-ctrl-geocoder--suggestion-address"
        ).click()
        region_field.send_keys(Keys.RETURN)

        time.sleep(1)
        buttons = self.driver.find_elements(By.CLASS_NAME, "css-1mtdczm")
        buttons[0].click()
        self.driver.find_element(By.CSS_SELECTOR, 'button[value="SHARED"]').click()
        # Close the type filter so the next one can open.
        buttons[0].click()

        # The price filter is applied through the URL.
        self.driver.get(self.driver.current_url + f"&max_price={self.profile.max_rent}")
        time.sleep(1 + TIME_DELAY_ON_LOAD)
        self.state = "SEARCHED"

    def gather_results(self) -> list[str]:
        """
        Collect the links to the listings on the results page.

        :return: Unique listing URLs.
        """
        valid_links = set()
        for link in self.driver.find_elements(By.XPATH, "//a[@href]"):
            url = link.get_attribute("href") or ""
            if "en/flat/" in url:
                valid_links.add(url)
        return sorted(valid_links)

    def visit_and_gather(self, url: str) -> tuple[str, str]:
        """
        Open one listing and read its description and details table.

        :param url: Listing URL from :meth:`gather_results`.
        :return: Listing id and the listing's HTML.
        :raises ValueError: If the URL has no listing id.
        """
        match = re.search(r"en/flat/(.*?)/\d+/", url)
        if not match:
            raise ValueError(f"No listing id in {url}")
        advertisement_id = match.group(1)

        self.driver.get(url)
        time.sleep(1)

        content = self.driver.find_element(By.CLASS_NAME, "markdown")
        table = self.driver.find_element(
            By.CSS_SELECTOR, "table.table--rows.table--fluid.table--fixed.table--flush"
        )
        html = (content.get_attribute("innerHTML") or "") + (
            table.get_attribute("innerHTML") or ""
        )
        return advertisement_id, html

    def send_information(self, message: str) -> None:
        """
        Post the contact form of the current listing with the browser's session.

        :param message: Body of the message to the landlord.
        :raises SendError: If Flatfox does not accept the request.
        """
        session = requests.Session()
        csrf_token = self.driver.find_element(
            By.NAME, "csrfmiddlewaretoken"
        ).get_attribute("value")
        for cookie in self.driver.get_cookies():
            session.cookies.set(cookie["name"], cookie["value"])

        headers = {"Referer": self.driver.current_url, "User-Agent": "Mozilla/5.0"}
        form_data = {
            "csrfmiddlewaretoken": csrf_token,
            "name": self.profile.user_name,
            "email": self.profile.flatfox_login,
            "phone_number": self.profile.user_phone_number,
            "text": message,
            "create_subscription": "off",
        }
        try:
            response = session.post(
                self.driver.current_url, data=form_data, headers=headers, timeout=30
            )
        except requests.RequestException as error:
            raise SendError(f"Flatfox request failed: {error}") from error
        if not response.ok:
            raise SendError(
                f"Flatfox rejected the message: HTTP {response.status_code}"
            )
        time.sleep(10)

    def close(self) -> None:
        """
        Quit Chrome.
        """
        self.driver.quit()
