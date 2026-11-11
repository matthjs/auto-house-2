"""
Selenium driver for wohnen.ethz.ch, the ETH/UZH housing office.
"""

import re
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from src.search_profile import SearchProfile

TIME_DELAY_ON_LOAD = 0.5
MAILTO = "mailto:"


def pick_contact_email(hrefs: list[str]) -> str | None:
    """
    Choose the landlord's address from the links on a listing page.

    :param hrefs: Every ``href`` on the page.
    :return: The single non-empty ``mailto:`` address, or ``None`` if there is none.
    :raises ValueError: If the page lists more than one different address.
    """
    emails = {
        href[len(MAILTO) :].strip()
        for href in hrefs
        if href and href.startswith(MAILTO) and href[len(MAILTO) :].strip()
    }
    if len(emails) > 1:
        raise ValueError(f"More than one email found: {sorted(emails)}")
    return emails.pop() if emails else None


class WohnenETHZWebInteractor:
    """
    Log in to wohnen.ethz.ch, search offers and read listing pages.

    Contact happens by email, so this class has no send step.
    """

    def __init__(self, profile: SearchProfile, headless: bool = False) -> None:
        """
        Start a Chrome session.

        :param profile: Profile with the wohnen.ethz.ch login and search settings.
        :param headless: Run Chrome without a window.
        """
        self.base_url = "https://wohnen.ethz.ch/index.php?act=searchoffer"
        self.profile = profile
        if headless:
            chrome_options = Options()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--window-size=1920,1080")
            self.driver = webdriver.Chrome(options=chrome_options)
        else:
            self.driver = webdriver.Chrome()
        self.state = "STARTING"

    def load(self) -> None:
        """
        Open the search page.
        """
        self.driver.get(self.base_url)
        time.sleep(TIME_DELAY_ON_LOAD)
        self.state = "LOADED"

    def enter(self) -> None:
        """
        Log in with the profile's credentials.
        """
        username_field = self.driver.find_element(By.NAME, "User")
        username_field.send_keys(self.profile.wohnen_ethz_login)
        password_field = self.driver.find_element(By.NAME, "Passwort")
        password_field.send_keys(self.profile.wohnen_ethz_password)
        password_field.send_keys(Keys.RETURN)
        time.sleep(TIME_DELAY_ON_LOAD)
        self.state = "ENTERED"

    def search(self) -> None:
        """
        Fill in the maximum rent and place, then submit the search.
        """
        rent_field = self.driver.find_element(By.NAME, "Miete")
        rent_field.send_keys(str(self.profile.max_rent))
        place_field = self.driver.find_element(By.NAME, "Ort")
        place_field.send_keys(self.profile.place)
        place_field.send_keys(Keys.RETURN)
        time.sleep(TIME_DELAY_ON_LOAD)
        self.state = "SEARCHED"

    def gather_results(self) -> list[str]:
        """
        Collect the links to the listings on the results page.

        :return: Listing URLs, in page order.
        """
        links = self.driver.find_elements(By.XPATH, "//a[@href]")
        valid_links = []
        for link in links:
            url = link.get_attribute("href") or ""
            if "https://wohnen.ethz.ch/index.php?act=detoffer&" in url:
                valid_links.append(url)
        self.state = "GOT LINKS"
        return valid_links

    def visit_and_gather(self, url: str) -> tuple[str, str | None, str]:
        """
        Open one listing and read its content and contact address.

        :param url: Listing URL from :meth:`gather_results`.
        :return: Listing id, landlord email (``None`` if the page has none) and the
            listing's HTML.
        :raises ValueError: If the URL has no ``pid`` or the page lists several
            different email addresses.
        """
        match = re.search(r"pid=(\d+)", url)
        if not match:
            raise ValueError(f"No listing id in {url}")
        pid = match.group(1)

        self.driver.get(url)
        time.sleep(TIME_DELAY_ON_LOAD)

        section = self.driver.find_element(By.ID, "contentContainer")
        html_content = section.get_attribute("innerHTML") or ""
        hrefs = [
            link.get_attribute("href") or ""
            for link in self.driver.find_elements(By.XPATH, "//a[@href]")
        ]
        return pid, pick_contact_email(hrefs), html_content

    def close(self) -> None:
        """
        Quit Chrome.
        """
        self.driver.quit()
