"""Contact hunting via free sources.

Strategy:
  1. Search DuckDuckGo HTML for `site:linkedin.com/in "<title>" "<company>"` patterns
     to surface LinkedIn profiles with name + title.
  2. Scrape the company's About/Team/Contact pages for emails and team listings.
  3. Generate firstname.lastname@domain permutations.
  4. Verify candidates by checking MX records (cheap, no SMTP probe to avoid
     getting flagged; SMTP verification is opt-in).

No paid APIs. Polite delays between requests.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from urllib.parse import quote_plus, urljoin, urlparse

import dns.resolver
import requests
import tldextract
from bs4 import BeautifulSoup

from .db import DB, Company, Contact

log = logging.getLogger(__name__)

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

INSURANCE_MIDDLE_MARKET_TITLES = [
    "Risk Manager", "Director of Risk Management", "VP Risk Management",
    "Chief Risk Officer", "CFO", "Chief Financial Officer",
    "Treasurer", "Controller", "General Counsel", "VP Finance",
    "Director of Insurance", "Insurance Manager", "Director of Operations",
    "COO", "VP Human Resources", "CHRO", "Director of HR",
]

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
LINKEDIN_PROFILE_RE = re.compile(r"linkedin\.com/in/[A-Za-z0-9\-_%]+")


@dataclass
class HuntResult:
    name: str | None
    title: str | None
    linkedin_url: str | None
    source: str
    company_name: str | None = None


class ContactHunter:
    def __init__(self, db: DB, user_agent: str = UA, request_delay: float = 1.5):
        self.db = db
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})
        self.delay = request_delay

    # ---------- public entry points ----------

    def hunt_company(self, company_name: str, domain: str | None = None,
                     titles: list[str] | None = None,
                     industry: str | None = None,
                     revenue_band: str | None = None) -> dict:
        """Find contacts at a company. Returns counts + IDs created."""
        titles = titles or INSURANCE_MIDDLE_MARKET_TITLES
        domain = (domain or self._guess_domain(company_name) or "").lower()

        company_id = self.db.upsert_company(Company(
            name=company_name, domain=domain or None,
            industry=industry, revenue_band=revenue_band,
        ))

        found: list[HuntResult] = []

        # 1. LinkedIn discovery via DuckDuckGo
        for title in titles:
            try:
                found.extend(self._search_linkedin(company_name, title))
                time.sleep(self.delay)
            except Exception as e:
                log.warning("linkedin search failed for %s/%s: %s",
                            company_name, title, e)

        # 2. Scrape company site for emails + about/team pages
        scraped_emails: set[str] = set()
        if domain:
            try:
                scraped_emails = self._scrape_company_site(domain)
            except Exception as e:
                log.warning("site scrape failed for %s: %s", domain, e)

        # 3. Persist linkedin findings + permute emails
        contact_ids: list[int] = []
        for r in found:
            first, last = self._split_name(r.name)
            if not first:
                continue
            email, confidence = None, 0.0
            if domain:
                # Generate permutations; prefer one that appears in scraped emails
                perms = self._email_permutations(first, last, domain)
                for p in perms:
                    if p in scraped_emails:
                        email, confidence = p, 0.95
                        break
                if not email:
                    # Pick most common pattern; verify MX
                    email = perms[0]
                    confidence = 0.5 if self._mx_exists(domain) else 0.2
            contact_ids.append(self.db.upsert_contact(Contact(
                first_name=first, last_name=last, title=r.title,
                email=email, email_confidence=confidence,
                linkedin_url=r.linkedin_url, source=r.source,
                company_id=company_id,
            )))

        # 4. Any emails found on the site that aren't matched to a contact -
        # save as generic/unknown contacts so the user can review
        for e in scraped_emails:
            if not self._email_already_known(contact_ids, e):
                first, last = self._guess_name_from_email(e)
                contact_ids.append(self.db.upsert_contact(Contact(
                    first_name=first, last_name=last, email=e,
                    email_confidence=0.9, source="company_site",
                    company_id=company_id,
                )))

        return {
            "company_id": company_id,
            "linkedin_hits": len(found),
            "scraped_emails": len(scraped_emails),
            "contacts_saved": len(contact_ids),
        }

    # ---------- LinkedIn via DuckDuckGo ----------

    def _search_linkedin(self, company: str, title: str) -> list[HuntResult]:
        q = f'site:linkedin.com/in "{title}" "{company}"'
        url = f"https://duckduckgo.com/html/?q={quote_plus(q)}"
        resp = self.session.get(url, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        results = []
        for a in soup.select("a.result__a, a.result__url"):
            href = a.get("href", "")
            m = LINKEDIN_PROFILE_RE.search(href)
            if not m:
                continue
            text = a.get_text(" ", strip=True)
            # DDG titles tend to look like: "Jane Doe - Risk Manager - Acme | LinkedIn"
            name = text.split(" - ")[0].split(" | ")[0].strip()
            results.append(HuntResult(
                name=name, title=title,
                linkedin_url="https://" + m.group(0),
                source="linkedin/ddg", company_name=company,
            ))
        return results

    # ---------- company site scrape ----------

    def _scrape_company_site(self, domain: str) -> set[str]:
        base = f"https://{domain}"
        urls = [base]
        try:
            r = self.session.get(base, timeout=10)
            soup = BeautifulSoup(r.text, "lxml")
            for a in soup.find_all("a", href=True):
                href = a["href"].lower()
                if any(k in href for k in ("about", "team", "leadership",
                                            "contact", "people", "staff")):
                    urls.append(urljoin(base, a["href"]))
        except Exception:
            pass

        emails: set[str] = set()
        for u in list(dict.fromkeys(urls))[:8]:
            try:
                r = self.session.get(u, timeout=10)
                for m in EMAIL_RE.findall(r.text):
                    e = m.lower()
                    # Filter obvious junk
                    if any(x in e for x in ("example.com", "sentry.io",
                                            "wixpress", "@2x", "@3x")):
                        continue
                    if domain not in e:
                        continue
                    emails.add(e)
                time.sleep(self.delay)
            except Exception as e:
                log.debug("scrape %s failed: %s", u, e)
        return emails

    # ---------- helpers ----------

    def _guess_domain(self, company: str) -> str | None:
        q = f"{company} official website"
        url = f"https://duckduckgo.com/html/?q={quote_plus(q)}"
        try:
            resp = self.session.get(url, timeout=10)
            soup = BeautifulSoup(resp.text, "lxml")
            for a in soup.select("a.result__a"):
                href = a.get("href", "")
                # DDG wraps links; extract target
                m = re.search(r"uddg=([^&]+)", href)
                target = m.group(1) if m else href
                ext = tldextract.extract(target)
                if ext.domain and ext.suffix:
                    cand = f"{ext.domain}.{ext.suffix}"
                    # skip social/linkedin/etc
                    if ext.domain not in ("linkedin", "facebook", "twitter",
                                          "x", "youtube", "duckduckgo",
                                          "wikipedia", "instagram"):
                        return cand
        except Exception as e:
            log.debug("domain guess failed: %s", e)
        return None

    @staticmethod
    def _split_name(name: str | None) -> tuple[str | None, str | None]:
        if not name:
            return None, None
        parts = [p for p in re.split(r"\s+", name.strip()) if p]
        if len(parts) >= 2:
            return parts[0], parts[-1]
        if parts:
            return parts[0], None
        return None, None

    @staticmethod
    def _email_permutations(first: str, last: str | None, domain: str) -> list[str]:
        f = first.lower()
        l = (last or "").lower()
        out = []
        if l:
            out += [
                f"{f}.{l}@{domain}",
                f"{f}{l}@{domain}",
                f"{f[0]}{l}@{domain}",
                f"{f}_{l}@{domain}",
                f"{f}-{l}@{domain}",
                f"{f}@{domain}",
                f"{l}@{domain}",
                f"{f[0]}.{l}@{domain}",
            ]
        else:
            out += [f"{f}@{domain}"]
        return list(dict.fromkeys(out))

    @staticmethod
    def _guess_name_from_email(email: str) -> tuple[str | None, str | None]:
        local = email.split("@", 1)[0]
        local = re.sub(r"\d+$", "", local)
        for sep in (".", "_", "-"):
            if sep in local:
                a, _, b = local.partition(sep)
                return a.title(), b.title()
        return local.title(), None

    @staticmethod
    def _mx_exists(domain: str) -> bool:
        try:
            answers = dns.resolver.resolve(domain, "MX", lifetime=5)
            return len(list(answers)) > 0
        except Exception:
            return False

    def _email_already_known(self, contact_ids: list[int], email: str) -> bool:
        for cid in contact_ids:
            row = self.db.get_contact(cid)
            if row and row.get("email") == email:
                return True
        return False
