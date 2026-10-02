"""
Legacy.com obituary scraper for King George County, Virginia.

Purpose:
- Pull King George County obituary listings from Legacy.com.
- Continue through the historical result pages until Legacy stops returning
  new records (with a safety cap).
- Write the records to data/obits/legacy.json for the VA property matcher.

This intentionally does NOT scrape Fredericksburg generally. The target is
King George County.
"""

import json
import logging
import os
import random
import re
import time
from datetime import datetime

import requests
from bs4 import BeautifulSoup

try:
    from curl_cffi import requests as _cffi_requests
    _HAS_CFFI = True
except ImportError:
    _cffi_requests = None
    _HAS_CFFI = False


logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

KING_GEORGE_URL = (
    "https://www.legacy.com/us/obituaries/local/virginia/king-george-county"
)

_STATE_NAMES = {
    "maryland": "MD",
    "md": "MD",
    "virginia": "VA",
    "va": "VA",
    "pennsylvania": "PA",
    "pa": "PA",
    "delaware": "DE",
    "de": "DE",
    "west virginia": "WV",
    "wv": "WV",
    "district of columbia": "DC",
    "washington, d.c.": "DC",
    "washington d.c.": "DC",
    "dc": "DC",
    "north carolina": "NC",
    "nc": "NC",
    "florida": "FL",
    "new jersey": "NJ",
    "new york": "NY",
}


def make_session():
    """Create a session that Legacy.com is likely to serve."""
    if _HAS_CFFI:
        session = _cffi_requests.Session(impersonate="chrome")
        session.headers.update({"Accept-Language": HEADERS["Accept-Language"]})
        return session

    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def _record_key(obit):
    """Stable key used to remove duplicate obituary listings."""
    person_id = str(obit.get("person_id") or "").strip()
    if person_id:
        return f"id:{person_id}"

    name = re.sub(
        r"\s+",
        " ",
        str(obit.get("full_name") or "").strip().lower()
    )
    dod = str(obit.get("date_of_death") or "").strip().lower()
    return f"name:{name}|dod:{dod}"


def _richness_score(obit):
    return sum(
        1
        for field in (
            "person_id",
            "date_of_death",
            "date_of_birth",
            "age",
            "city",
            "obituary_text",
            "obituary_url",
        )
        if obit.get(field)
    )


def scrape_legacy_obituaries(max_pages=100):
    """
    Scrape the King George County Legacy.com local archive.

    The scraper stops when:
    - a page returns no obituary records, OR
    - Legacy starts repeating a page we already saw, OR
    - max_pages is reached as a safety limit.
    """
    session = make_session()
    by_key = {}
    seen_page_fingerprints = set()

    for page in range(1, max_pages + 1):
        try:
            logger.info("Scraping King George County page %s", page)

            response = session.get(
                KING_GEORGE_URL,
                params={"page": page},
                timeout=25,
            )

            if response.status_code != 200:
                logger.warning(
                    "Legacy returned HTTP %s on page %s; stopping.",
                    response.status_code,
                    page,
                )
                break

            page_obits = _extract_obituaries_json(
                response.text,
                "county/king-george-county",
            )

            if not page_obits:
                page_obits = _extract_obituaries_html(
                    response.text,
                    "county/king-george-county",
                )

            # Keep Virginia records and records where Legacy did not provide
            # an explicit state. The source page itself is King George County.
            page_obits = [
                obit
                for obit in page_obits
                if str(obit.get("state") or "").strip()
                in ("", "VA", "Virginia")
            ]

            if not page_obits:
                logger.info(
                    "No obituary records found on page %s; archive complete.",
                    page,
                )
                break

            page_keys = tuple(sorted(_record_key(obit) for obit in page_obits))
            if page_keys in seen_page_fingerprints:
                logger.info(
                    "Legacy repeated a previously seen result page at page %s; "
                    "stopping to avoid a loop.",
                    page,
                )
                break

            seen_page_fingerprints.add(page_keys)

            new_count = 0

            for obit in page_obits:
                key = _record_key(obit)
                existing = by_key.get(key)

                if existing is None:
                    by_key[key] = obit
                    new_count += 1
                elif _richness_score(obit) > _richness_score(existing):
                    by_key[key] = obit

            logger.info(
                "Page %s: %s records, %s new; total unique now %s",
                page,
                len(page_obits),
                new_count,
                len(by_key),
            )

            # If a page contained records but none were new, Legacy is most
            # likely repeating its last available page.
            if new_count == 0:
                logger.info(
                    "Page %s contained no new records; archive traversal complete.",
                    page,
                )
                break

            time.sleep(random.uniform(1.2, 2.2))

        except Exception as exc:
            logger.error("Error scraping King George page %s: %s", page, exc)
            break

    records = list(by_key.values())

    records.sort(
        key=lambda row: (
            str(row.get("date_of_death") or ""),
            str(row.get("last_name") or ""),
            str(row.get("first_name") or ""),
        ),
        reverse=True,
    )

    logger.info("Total unique King George Legacy obituaries: %s", len(records))
    return records


def _extract_obituaries_json(html, source_label):
    """
    Extract Legacy's richer embedded obituary JSON arrays.
    """
    obituaries = []
    search_start = 0
    all_raw_obits = []

    try:
        while True:
            idx = html.find('"obituaries":[', search_start)
            if idx == -1:
                break

            nearby = html[idx:idx + 500]
            before = html[max(0, idx - 400):idx]

            # Ignore Legacy's nationwide "Notable Obituaries" widget.
            if "celebrity-deaths" in before or "Notable Obituaries" in before:
                search_start = idx + 1
                continue

            if '"personId"' in nearby:
                arr_start = idx + len('"obituaries":')
                depth = 0
                end_idx = None

                for i in range(
                    arr_start,
                    min(len(html), arr_start + 500000),
                ):
                    if html[i] == "[":
                        depth += 1
                    elif html[i] == "]":
                        depth -= 1
                        if depth == 0:
                            end_idx = i + 1
                            break

                if end_idx:
                    json_string = html[arr_start:end_idx]
                    try:
                        raw_obits = json.loads(json_string)
                        all_raw_obits.extend(raw_obits)
                    except json.JSONDecodeError as exc:
                        logger.debug(
                            "Embedded JSON parse error for %s: %s",
                            source_label,
                            exc,
                        )

            search_start = idx + 1

        for raw in all_raw_obits:
            parsed = _parse_json_obituary(raw, source_label)
            if parsed and parsed.get("full_name"):
                obituaries.append(parsed)

    except Exception as exc:
        logger.error(
            "Error extracting embedded obituary data for %s: %s",
            source_label,
            exc,
        )

    return obituaries


def _extract_obituaries_html(html, source_label):
    """
    Fallback parser for Legacy's server-rendered obituary cards.
    """
    obituaries = []

    try:
        soup = BeautifulSoup(html, "html.parser")
        seen_person_ids = set()

        for anchor in soup.select('a[href*="legacy.com/person/"]'):
            href = anchor.get("href", "")

            person_match = re.search(r"/person/[^/?#]*?-(\d+)$", href)
            if not person_match:
                continue

            person_id = person_match.group(1)
            if person_id in seen_person_ids:
                continue

            name_element = anchor.select_one(".font-serif")
            if not name_element:
                continue

            seen_person_ids.add(person_id)

            full_name = name_element.get_text(" ", strip=True)

            years_element = anchor.select_one("span.font-semibold")
            years = years_element.get_text(strip=True) if years_element else ""

            date_of_birth = ""
            date_of_death = ""

            year_match = re.match(r"(\d{4})\s*-\s*(\d{4})", years)
            if year_match:
                date_of_birth = year_match.group(1)
                date_of_death = year_match.group(2)
            elif re.fullmatch(r"\d{4}", years):
                date_of_death = years

            snippet_element = anchor.select_one("p[title]")
            snippet = ""
            if snippet_element:
                snippet = (
                    snippet_element.get("title")
                    or snippet_element.get_text(" ", strip=True)
                )

            age = None
            city = ""
            state = ""

            location_match = re.search(
                r",?\s*(?:age\s+)?(\d{1,3}),?\s+of\s+"
                r"([A-Z][A-Za-z .'\-]+?),\s*"
                r"([A-Z][A-Za-z .]+?)[,.]",
                snippet,
            )

            if location_match:
                age = int(location_match.group(1))
                city = location_match.group(2).strip()
                raw_state = location_match.group(3).strip()
                state = _STATE_NAMES.get(
                    raw_state.lower(),
                    raw_state[:2].upper(),
                )
            else:
                va_match = re.search(
                    r"\bof\s+([A-Z][A-Za-z .'\-]+?),\s*(Virginia|VA)\b",
                    snippet,
                )
                if va_match:
                    city = va_match.group(1).strip()
                    state = "VA"

            obituary_url = ""

            card = anchor.find_parent("div")
            for _ in range(5):
                if card is None:
                    break

                ids = {
                    match.group(1)
                    for item in card.select('a[href*="legacy.com/person/"]')
                    if (
                        match := re.search(
                            r"-(\d+)$",
                            item.get("href", ""),
                        )
                    )
                }

                if len(ids) > 1:
                    break

                outbound = card.select_one(
                    'a[href*="/us/obituaries/name/"]'
                )
                if outbound:
                    obituary_url = outbound.get("href", "")
                    break

                card = card.find_parent("div")

            clean_name = re.sub(
                r"\s*\([^)]*\)",
                "",
                full_name,
            ).strip()

            name_parts = [
                part
                for part in clean_name.replace(",", " ").split()
                if part
            ]

            suffixes = {
                "jr",
                "jr.",
                "sr",
                "sr.",
                "ii",
                "iii",
                "iv",
            }

            while name_parts and name_parts[-1].lower() in suffixes:
                name_parts.pop()

            first_name = name_parts[0] if name_parts else ""
            last_name = name_parts[-1] if len(name_parts) > 1 else ""
            middle_name = (
                " ".join(name_parts[1:-1])
                if len(name_parts) > 2
                else ""
            )

            obituaries.append(
                {
                    "full_name": full_name,
                    "first_name": first_name,
                    "last_name": last_name,
                    "middle_name": middle_name,
                    "date_of_death": date_of_death,
                    "date_of_birth": date_of_birth,
                    "age": age,
                    "city": city,
                    "state": state,
                    "obituary_url": obituary_url or href,
                    "obituary_text": snippet,
                    "survived_by": "",
                    "source": f"Legacy.com/{source_label}",
                    "person_id": person_id,
                }
            )

    except Exception as exc:
        logger.error(
            "HTML parsing error for %s: %s",
            source_label,
            exc,
        )

    return obituaries


def _parse_json_obituary(raw, source_label):
    """
    Parse a Legacy embedded obituary record into the fields expected by
    the Virginia matcher.
    """
    try:
        name_data = raw.get("name", {})

        if isinstance(name_data, dict) and name_data.get("fullName"):
            location_data = raw.get("location", {})
            if not isinstance(location_data, dict):
                location_data = {}

            city_data = location_data.get("city", {})
            state_data = location_data.get("state", {})

            links_data = raw.get("links", {})
            if not isinstance(links_data, dict):
                links_data = {}

            obituary_url_data = links_data.get("obituaryUrl", {})

            full_name = name_data.get("fullName", "")
            first_name = name_data.get("firstName", "")
            last_name = name_data.get("lastName", "")
            middle_name = name_data.get("middleName", "") or ""

            date_of_birth = ""
            date_of_death = ""

            from_to = raw.get("fromToYears", "")
            if from_to and " - " in str(from_to):
                parts = str(from_to).split(" - ")
                if len(parts) == 2:
                    date_of_birth = parts[0].strip()
                    date_of_death = parts[1].strip()

            if isinstance(obituary_url_data, dict):
                obituary_url = obituary_url_data.get("href", "")
            elif isinstance(obituary_url_data, str):
                obituary_url = obituary_url_data
            else:
                obituary_url = ""

            if isinstance(city_data, dict):
                city = city_data.get("fullName") or ""
            else:
                city = str(city_data) if city_data else ""

            if isinstance(state_data, dict):
                state = state_data.get("code") or "VA"
            else:
                state = str(state_data) if state_data else "VA"

            return {
                "full_name": full_name,
                "first_name": first_name,
                "last_name": last_name,
                "middle_name": middle_name,
                "date_of_death": date_of_death,
                "date_of_birth": date_of_birth,
                "age": raw.get("age"),
                "city": city,
                "state": state,
                "obituary_url": obituary_url,
                "obituary_text": raw.get("obitSnippet", "") or "",
                "survived_by": "",
                "source": f"Legacy.com/{source_label}",
                "person_id": str(raw.get("personId", "")),
            }

        # Fallback Legacy schema.
        title = raw.get("title", "")
        link = raw.get("link", "")

        if title and link:
            full_name = title
            date_of_birth = ""
            date_of_death = ""

            years_match = re.match(
                r"^(.*?)\s*\((\d{4})\s*-\s*(\d{4})\)\s*$",
                title,
            )

            if years_match:
                full_name = years_match.group(1).strip()
                date_of_birth = years_match.group(2)
                date_of_death = years_match.group(3)
            else:
                death_year_match = re.match(
                    r"^(.*?)\s*\((\d{4})\)\s*$",
                    title,
                )
                if death_year_match:
                    full_name = death_year_match.group(1).strip()
                    date_of_death = death_year_match.group(2)

            name_parts = full_name.split()
            first_name = name_parts[0] if name_parts else ""
            last_name = name_parts[-1] if len(name_parts) > 1 else ""
            middle_name = (
                " ".join(name_parts[1:-1])
                if len(name_parts) > 2
                else ""
            )

            return {
                "full_name": full_name,
                "first_name": first_name,
                "last_name": last_name,
                "middle_name": middle_name,
                "date_of_death": date_of_death,
                "date_of_birth": date_of_birth,
                "age": None,
                "city": "",
                "state": "VA",
                "obituary_url": link,
                "obituary_text": "",
                "survived_by": "",
                "source": f"Legacy.com/{source_label}",
                "person_id": "",
            }

    except Exception as exc:
        logger.debug("Error parsing Legacy obituary JSON: %s", exc)

    return None


def _extract_year(value):
    """Return a plausible four-digit year from a date/year string."""
    if not value:
        return None

    match = re.search(r"\b(19\d{2}|20\d{2})\b", str(value))
    if not match:
        return None

    return int(match.group(1))


def save_records(records):
    os.makedirs("data/obits", exist_ok=True)
    output_path = "data/obits/legacy.json"

    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(records, handle, indent=2, ensure_ascii=False)

    years = [
        year
        for year in (_extract_year(r.get("date_of_death")) for r in records)
        if year is not None
    ]

    print(f"Saved {len(records)} King George Legacy obituaries to {output_path}")

    if years:
        print(
            f"Death-year range found in records: "
            f"{min(years)} through {max(years)}"
        )
    else:
        print("No usable death years were found in the listing data.")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    records = scrape_legacy_obituaries(max_pages=100)
    save_records(records)
