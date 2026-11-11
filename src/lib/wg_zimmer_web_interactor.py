"""
Selenium driver for wgzimmer.ch.

wgzimmer.ch blocks plain Selenium, so this uses undetected-chromedriver.
"""

import os
import re
import time

import undetected_chromedriver as uc
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from src.lib.errors import SendError
from src.personal_profile import PersonalProfile

TIME_DELAY_ON_LOAD = 2
LISTING_SECTIONS = [
    "date-cost",
    "adress-region",
    "mate-content nbb",
    "room-content",
    "person-content",
]


class WGZimmerWebInteractor:
    """
    Search wgzimmer.ch and walk through the results with the "next" link.

    Unlike the other sites, results are read one at a time: each listing page links
    to the next one, so call :meth:`visit_and_gather` while :attr:`has_next_link`.
    """

    def __init__(self, profile: PersonalProfile) -> None:
        """
        Start an undetected Chrome session.

        Set ``CHROME_VERSION_MAIN`` (for example ``142``) if the driver does not match
        your installed Chrome; otherwise it is detected automatically.

        :param profile: Profile with the search settings and contact details.
        """
        self.base_url = "https://www.wgzimmer.ch/wgzimmer/search/mate.html"
        self.profile = profile

        options = uc.ChromeOptions()
        options.add_argument("--disable-blink-features=AutomationControlled")
        version_main = os.environ.get("CHROME_VERSION_MAIN")
        self.driver = uc.Chrome(
            options=options,
            version_main=int(version_main) if version_main else None,
        )

        self.next_link: str | None = None
        self.has_next_link = False
        self.current_url: str | None = None
        self.state = "STARTING"

    def load(self) -> None:
        """
        Open the search page and accept the cookie banner.
        """
        self.driver.get(self.base_url)
        # Needs the longer delay, otherwise the cookie button is not clickable yet.
        time.sleep(TIME_DELAY_ON_LOAD)
        consent_button = self.driver.find_element(
            By.CSS_SELECTOR, "button.fc-button.fc-cta-consent.fc-primary-button"
        )
        consent_button.click()
        time.sleep(TIME_DELAY_ON_LOAD)
        self.state = "LOADED"

    def enter(self) -> None:
        """
        Fill in the search form: price range, region and permanent rooms only.
        """
        self._select_option("priceMin", "200")
        self._select_option("priceMax", str(self.profile.max_rent_wg_zimmer))
        self._select_option("wgState", self.profile.place_wg_zimmer)
        self.driver.find_element(By.ID, "permanent").click()
        self.state = "FORM_FILLED"

    def _select_option(self, name: str, value: str) -> None:
        """
        Pick a value in a ``<select>`` on the search form.

        :param name: The select element's ``name`` attribute.
        :param value: The option's ``value`` attribute.
        """
        dropdown = self.driver.find_element(By.NAME, name)
        for option in dropdown.find_elements(By.TAG_NAME, "option"):
            if option.get_attribute("value") == value:
                option.click()
                return

    def search(self) -> None:
        """
        Submit the search form.
        """
        search_field = self.driver.find_element(By.NAME, "query")
        search_field.send_keys(Keys.RETURN)
        time.sleep(TIME_DELAY_ON_LOAD)
        self.state = "ENTERED"

    def gather_results(self) -> None:
        """
        Find the first listing on the results page and queue it as the next link.
        """
        for link in self.driver.find_elements(By.XPATH, "//a[@href]"):
            url = link.get_attribute("href") or ""
            if "https://www.wgzimmer.ch/wglink/" in url and "facebook" not in url:
                self.next_link = url
                self.has_next_link = True
                break
        self.state = "GOT LINKS"

    def visit_and_gather(self) -> tuple[str, str]:
        """
        Open the queued listing, read it, and queue the listing after it.

        Sets :attr:`has_next_link` to ``False`` on the last listing.

        :return: Listing id and the listing's text.
        :raises ValueError: If there is no queued listing or its URL has no id.
        """
        if not self.next_link:
            raise ValueError("No listing queued; call gather_results() first")
        match = re.search(r"/de/([a-z0-9\-]+)/", self.next_link)
        if not match:
            raise ValueError(f"No listing id in {self.next_link}")
        pid = match.group(1)

        self.current_url = self.next_link
        self.driver.get(self.next_link)
        time.sleep(TIME_DELAY_ON_LOAD)

        sections = []
        for class_name in LISTING_SECTIONS:
            elements = self.driver.find_elements(
                By.XPATH, f"//div[contains(@class, '{class_name}')]/p"
            )
            if elements:
                sections.append(elements[0].text)

        next_elements = self.driver.find_elements(By.CLASS_NAME, "next")
        self.next_link = (
            next_elements[0].get_attribute("href") if next_elements else None
        )
        self.has_next_link = bool(self.next_link)

        return pid, "\n".join(sections)

    def send_information(self, message: str) -> None:
        """
        Fill in and submit the contact form on the current listing.

        :param message: Body of the message to the landlord.
        :raises SendError: If the form cannot be found or submitted.
        """
        try:
            contact_button = self.driver.find_element(
                By.XPATH, "//a[contains(@onclick, 'showContactDetail')]"
            )
            contact_button.click()
            time.sleep(TIME_DELAY_ON_LOAD)

            self.driver.find_element(By.ID, "senderName").send_keys(
                self.profile.user_name
            )
            self.driver.find_element(By.ID, "senderEmail").send_keys(
                self.profile.user_email
            )
            self.driver.find_element(By.ID, "senderPhone").send_keys(
                self.profile.user_phone_number
            )
            self.driver.find_element(By.ID, "senderText").send_keys(message)

            send_button = self.driver.find_element(By.CLASS_NAME, "submit-inline-mail")
            try:
                send_button.click()
            except WebDriverException:
                ActionChains(self.driver).move_to_element(send_button).click().perform()
        except WebDriverException as error:
            raise SendError(
                f"Could not submit the wgzimmer.ch form: {error}"
            ) from error
        # Known issue: the click sometimes misses without raising, so the message is
        # not sent. There is no confirmation element to check yet.
        time.sleep(TIME_DELAY_ON_LOAD)

    def close(self) -> None:
        """
        Quit Chrome.
        """
        self.driver.quit()
