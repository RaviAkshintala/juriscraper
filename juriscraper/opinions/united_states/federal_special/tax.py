# Scraper for the United States Tax Court
# CourtID: tax
# Court Short Name: Tax Ct.
# Neutral Citation Format (Tax Court opinions): 138 T.C. No. 1 (2012)
# Neutral Citation Format (Memorandum opinions): T.C. Memo 2012-1
# Neutral Citation Format (Summary opinions: T.C. Summary Opinion 2012-1

import os
import re
from datetime import date, datetime, timedelta

from dateutil.rrule import WEEKLY, rrule
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

from juriscraper.AbstractSite import logger, phantomjs_executable_path
from juriscraper.OpinionSite import OpinionSite
from juriscraper.lib.html_utils import fix_links_but_keep_anchors
from juriscraper.lib.models import citation_types


class Site(OpinionSite):
    def __init__(self, *args, **kwargs):
        super(Site, self).__init__(*args, **kwargs)
        self.uses_selenium = True
        self.url = "https://www.ustaxcourt.gov/UstcInOp/OpinionSearch.aspx"
        self.base_path = '//tr[@class="ResultsOddRow" or ' '@class="ResultsEvenRow"]'
        self.case_date = date.today()
        self.backwards_days = 14
        self.back_scrape_iterable = [
            i.date()
            for i in rrule(WEEKLY, dtstart=date(1995, 9, 25), until=date(2018, 11, 13),)
        ]

        self.court_id = self.__module__

    def _download(self, request_dict={}):
        """Uses Selenium because doing it with requests is a pain."""
        if self.test_mode_enabled():
            return super(Site, self)._download(request_dict=request_dict)

        driver = webdriver.PhantomJS(
            executable_path=phantomjs_executable_path,
            service_log_path=os.path.devnull,  # Disable ghostdriver.log
        )
        driver.implicitly_wait(30)
        logger.info("Now downloading case page at: %s" % self.url)
        driver.get(self.url)

        # Set the start and end dates
        start_date_id = "ctl00_Content_dpDateSearch_dateInput"
        start_date_input = driver.find_element_by_id(start_date_id)
        start_date_input.send_keys(
            (self.case_date - timedelta(days=self.backwards_days)).strftime(
                "%-m/%-d/%Y"
            )
        )

        end_date_id = "ctl00_Content_dpDateSearchTo_dateInput"
        end_date_input = driver.find_element_by_id(end_date_id)
        end_date_input.send_keys(self.case_date.strftime("%-m/%-d/%Y"))
        # driver.save_screenshot('%s.png' % self.case_date)

        # Check ordering by case date (this orders by case date, *ascending*)
        ordering_id = "Content_rdoCaseName_1"
        driver.find_element_by_id(ordering_id).click()

        # Submit
        driver.find_element_by_id("Content_btnSearch").click()

        # Do not proceed until the results show up.
        wait = WebDriverWait(driver, 10)
        wait.until(EC.presence_of_element_located((By.ID, "Content_ddlResultsPerPage")))
        # driver.save_screenshot('with-results.png')

        text = self._clean_text(driver.page_source)
        driver.quit()
        html_tree = self._make_html_tree(text)
        html_tree.rewrite_links(fix_links_but_keep_anchors, base_href=self.url)
        return html_tree

    def _get_download_urls(self):
        # URLs here take two forms. For precedential cases, they're simple, and
        # look like:
        #   https://www.ustaxcourt.gov/UstcInOp/OpinionViewer.aspx?ID=11815
        # But for non-precedential cases, they have an annoying JS thing, and
        # links look like:
        #   https://www.ustaxcourt.gov/UstcInOp/OpinionSearch.aspx#11813
        # Note the hash instead of the ID.
        #
        # This is annoying, but we just have to swap out the ending and it
        # should be fine.
        hrefs = []
        path = self.base_path + "//@href"
        for href in self.html.xpath(path):
            if "?ID" in href:
                hrefs.append(href)
            else:
                hrefs.append(
                    href.replace("OpinionSearch.aspx#", "OpinionViewer.aspx?ID=")
                )
        return hrefs

    def _get_case_names(self):
        case_names = []
        path = self.base_path + "//td[1]"
        for td in self.html.xpath(path):
            case_names.append(td.text_content().strip() + " v. Commissioner")
        return case_names

    def _get_case_name_shorts(self):
        # The normal values are particularly bad, usually just returning
        # "Commissioner" for all cases. Just nuke these values.
        return [""] * len(self.case_names)

    def _get_precedential_statuses(self):
        statuses = []
        path = self.base_path + "//td[2]"
        for td in self.html.xpath(path):
            status = td.text_content().strip().lower()
            if "opinion" in status:
                statuses.append("Published")
            elif "memorandum" in status:
                statuses.append("Unpublished")
            elif "summary" in status:
                statuses.append("Unpublished")
            else:
                statuses.append("Unknown")
        return statuses

    def _get_case_dates(self):
        dates = []
        path = self.base_path + "//td[3]"
        for td in self.html.xpath(path):
            date_string = td.text_content().strip()
            dates.append(datetime.strptime(date_string, "%m/%d/%Y").date())
        return dates

    def _download_backwards(self, d):
        self.backwards_days = 7
        self.case_date = d
        logger.info(
            "Running backscraper with date range: %s to %s",
            self.case_date - timedelta(days=self.backwards_days),
            self.case_date,
        )
        self.html = self._download()
        if self.html is not None:
            # Setting status is important because it prevents the download
            # function from being run a second time by the parse method.
            self.status = 200

    def extract_from_text(self, scraped_text):
        """Can we extract the citation and related information

        :param scraped_text: The content of the docuemnt downloaded
        :return: dictionary of citations, reporter, volume and page
        """
        metadata = {
            "Citation": {"type": citation_types["SPECIALTY"]},
            "OpinionCluster": {"precedential_status": ""},
        }

        tax_court_reports_regex = re.compile(
            r"""
            ([0-9]{1,4})\s{1,}                           # (volume)
            UNITED\ STATES\ TAX\ COURT\ REPORTS?\s{1,}   # (reporter)
            \((\d{1,4})\)                                # (page)
            """,
            re.VERBOSE | re.IGNORECASE,
        )

        tax_court_alt_regex = re.compile(
            r"""
            ((T\.\ ?C\.\s((Memo\.?)|(Summary\ Opinion))\s{1,}   # T.C. Memo or Summary Opinion (reporter)
            ([0-9]{4})                                          # Four digit year (volume)
            .                                                   # hyphen, em-dash etc.
            ([0-9]{1,3})\b)                                     # 1-3 digit number in order of publication (page)
            |                                                   # or 
            ([0-9]{1,4})\s{1,}                                  # (volume)
            (T\.\ ?C\.\ No\.)\s{1,}                             # T.C. No. (reporter)
            (\d{1,4}))                                          # (page)
            """,
            re.VERBOSE | re.IGNORECASE,
        )

        match = re.search(tax_court_reports_regex, scraped_text)

        if match:
            metadata["Citation"]["volume"] = match.group(1)
            metadata["Citation"]["page"] = match.group(2)
            metadata["Citation"]["reporter"] = "T.C."
            metadata["OpinionCluster"]["precedential_status"] = "Published"
        else:
            match = re.search(tax_court_alt_regex, scraped_text)
            if match:
                if "No." in match.group():
                    metadata["Citation"]["reporter"] = "T.C."
                    metadata["Citation"]["volume"] = match.group(8)
                    metadata["Citation"]["page"] = match.group(10)
                    metadata["OpinionCluster"]["precedential_status"] = "Published"
                else:
                    if "Memo" in match.group():
                        metadata["Citation"]["reporter"] = "T.C. Memo."
                    elif "Summary" in match.group():
                        metadata["Citation"]["reporter"] = "T.C. Summary Opinion"
                    metadata["Citation"]["volume"] = match.group(6)
                    metadata["Citation"]["page"] = match.group(7)
                    metadata["OpinionCluster"]["precedential_status"] = "Unpublished"

        return metadata
