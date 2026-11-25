import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from email.utils import parsedate_to_datetime

CONFIG_FILE = "feeds.json"
OUTPUT_FILE = "feed.xml"
MAX_ITEMS = 50


def download_feed(url):
    request = Request(
        url,
        headers={
            "User-Agent": "G6-Austral-RSS/1.0"
        }
    )

    with urlopen(request, timeout=20) as response:
        return response.read()


def parse_date(value):
    if not value:
        return datetime.now(timezone.utc)

    try:
        return parsedate_to_datetime(value).astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def parse_feed(xml_data, source_name):
    root = ET.fromstring(xml_data)

    items = []

    # RSS tradicional
    for item in root.findall(".//item"):
        title = item.findtext("title", "").strip()
        link = item.findtext("link", "").strip()
        description = item.findtext("description", "").strip()
        pub_date = item.findtext("pubDate", "").strip()

        if title and link:
            items.append({
                "title": title,
                "link": link,
                "description": description,
                "date": parse_date(pub_date),
                "source": source_name
            })

    # Atom
    namespace = "{http://www.w3.org/2005/Atom}"

    for entry in root.findall(f".//{namespace}entry"):
        title_element = entry.find(f"{namespace}title")
        title = title_element.text.strip() if title_element is not None and title_element.text else ""

        link = ""

        for link_element in entry.findall(f"{namespace}link"):
            href = link_element.attrib.get("href")
            if href:
                link = href
                break

        summary_element = entry.find(f"{namespace}summary")
        description = (
            summary_element.text.strip()
            if summary_element is not None and summary_element.text
            else ""
        )

        updated_element = entry.find(f"{namespace}updated")
        updated = (
            updated_element.text.strip()
            if updated_element is not None and updated_element.text
            else ""
        )

        if title and link:
            try:
                date = datetime.fromisoformat(updated.replace("Z", "+00:00"))
            except Exception:
                date = datetime.now(timezone.utc)

            items.append({
                "title": title,
                "link": link,
                "description": description,
                "date": date,
                "source": source_name
            })

    return items


def clean_text(text):
    if not text:
        return ""

    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
    )


def main():
    with open(CONFIG_FILE, "r", encoding="utf-8") as file:
        config = json.load(file)

    all_items = []

    for feed in config["feeds"]:
        try:
            print(f"Leyendo: {feed['name']}")

            xml_data = download_feed(feed["url"])
            items = parse_feed(xml_data, feed["name"])

            all_items.extend(items)

            print(f"  Noticias encontradas: {len(items)}")

        except Exception as error:
            print(f"  ERROR: {error}")

    # Ordenar de más reciente a más antigua
    all_items.sort(
        key=lambda item: item["date"],
        reverse=True
    )

    # Eliminar noticias repetidas por URL
    unique_items = []
    seen_links = set()

    for item in all_items:
        if item["link"] not in seen_links:
            seen_links.add(item["link"])
            unique_items.append(item)

    unique_items = unique_items[:MAX_ITEMS]

    rss = ET.Element(
        "rss",
        {
            "version": "2.0",
            "xmlns:atom": "http://www.w3.org/2005/Atom"
        }
    )

    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = "G6 Austral — Últimas Noticias"

    ET.SubElement(
        channel,
        "link"
    ).text = "https://g6austral.cl"

    ET.SubElement(
        channel,
        "description"
    ).text = "Noticias de Chile e internacionales seleccionadas por G6 Austral."

    ET.SubElement(
        channel,
        "language"
    ).text = "es-CL"

    ET.SubElement(
        channel,
        "lastBuildDate"
    ).text = datetime.now(timezone.utc).strftime(
        "%a, %d %b %Y %H:%M:%S +0000"
    )

    for item in unique_items:
        rss_item = ET.SubElement(channel, "item")

        ET.SubElement(
            rss_item,
            "title"
        ).text = item["title"]

        ET.SubElement(
            rss_item,
            "link"
        ).text = item["link"]

        ET.SubElement(
            rss_item,
            "description"
        ).text = item["description"]

        ET.SubElement(
            rss_item,
            "pubDate"
        ).text = item["date"].strftime(
            "%a, %d %b %Y %H:%M:%S +0000"
        )

        ET.SubElement(
            rss_item,
            "source"
        ).text = item["source"]

    tree = ET.ElementTree(rss)

    ET.indent(tree, space="  ")

    tree.write(
        OUTPUT_FILE,
        encoding="utf-8",
        xml_declaration=True
    )

    print(f"\nRSS creado correctamente: {OUTPUT_FILE}")
    print(f"Noticias incluidas: {len(unique_items)}")


if __name__ == "__main__":
    main()
