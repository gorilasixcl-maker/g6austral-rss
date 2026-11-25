import json
import re
import html
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from email.utils import parsedate_to_datetime
from difflib import SequenceMatcher

CONFIG_FILE = "feeds.json"
OUTPUT_FILE = "feed.xml"

MAX_ITEMS = 100

# Mientras más alto, más estricta es la detección.
# 0.82 = bastante conservador.
DUPLICATE_THRESHOLD = 0.82


def download_feed(url):
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; G6-Austral-RSS/1.0)"
        }
    )

    with urlopen(request, timeout=30) as response:
        return response.read()


def parse_date(value):
    if not value:
        return datetime.now(timezone.utc)

    try:
        return parsedate_to_datetime(value).astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def clean_text(text):
    if not text:
        return ""

    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def normalize_title(title):
    """
    Normaliza un titular para poder compararlo
    con otros titulares de distintas fuentes.
    """

    title = clean_text(title).lower()

    # Eliminar puntuación
    title = re.sub(r"[^\w\sáéíóúüñ]", " ", title)

    # Eliminar espacios repetidos
    title = re.sub(r"\s+", " ", title).strip()

    # Palabras muy frecuentes que aportan poco
    stopwords = {
        "de", "la", "el", "los", "las",
        "un", "una", "unos", "unas",
        "y", "o", "en", "por", "para",
        "con", "del", "al", "se", "su",
        "sus", "que", "a"
    }

    words = [
        word
        for word in title.split()
        if word not in stopwords
    ]

    return " ".join(words)


def titles_are_duplicate(title_a, title_b):
    normalized_a = normalize_title(title_a)
    normalized_b = normalize_title(title_b)

    if not normalized_a or not normalized_b:
        return False

    # Coincidencia exacta después de normalizar
    if normalized_a == normalized_b:
        return True

    similarity = SequenceMatcher(
        None,
        normalized_a,
        normalized_b
    ).ratio()

    return similarity >= DUPLICATE_THRESHOLD


def parse_feed(xml_data, source_name):
    root = ET.fromstring(xml_data)

    items = []

    # RSS
    for item in root.findall(".//item"):

        title = item.findtext("title", "").strip()
        link = item.findtext("link", "").strip()
        description = item.findtext("description", "").strip()
        pub_date = item.findtext("pubDate", "").strip()

        if title and link:
            items.append({
                "title": clean_text(title),
                "link": link,
                "description": clean_text(description),
                "date": parse_date(pub_date),
                "source": source_name
            })

    # Atom
    namespace = "{http://www.w3.org/2005/Atom}"

    for entry in root.findall(f".//{namespace}entry"):

        title_element = entry.find(f"{namespace}title")

        title = (
            title_element.text.strip()
            if title_element is not None and title_element.text
            else ""
        )

        link = ""

        for link_element in entry.findall(f"{namespace}link"):
            href = link_element.attrib.get("href")

            if href:
                link = href
                break

        summary_element = entry.find(
            f"{namespace}summary"
        )

        description = (
            summary_element.text.strip()
            if summary_element is not None and summary_element.text
            else ""
        )

        updated_element = entry.find(
            f"{namespace}updated"
        )

        updated = (
            updated_element.text.strip()
            if updated_element is not None and updated_element.text
            else ""
        )

        if title and link:

            try:
                date = datetime.fromisoformat(
                    updated.replace("Z", "+00:00")
                )

            except Exception:
                date = datetime.now(timezone.utc)

            items.append({
                "title": clean_text(title),
                "link": link,
                "description": clean_text(description),
                "date": date,
                "source": source_name
            })

    return items


def remove_duplicates(items):

    # Primero ordenar por fecha
    items.sort(
        key=lambda item: item["date"],
        reverse=True
    )

    unique_items = []

    seen_links = set()

    for item in items:

        # --------------------------------
        # NIVEL 1: URL EXACTAMENTE IGUAL
        # --------------------------------

        if item["link"] in seen_links:
            continue

        # --------------------------------
        # NIVEL 2: TITULARES SIMILARES
        # --------------------------------

        duplicate_found = False

        for existing in unique_items:

            if titles_are_duplicate(
                item["title"],
                existing["title"]
            ):

                duplicate_found = True

                print(
                    "Duplicado detectado:"
                )

                print(
                    f"  NUEVO: {item['title']}"
                )

                print(
                    f"  ORIGINAL: {existing['title']}"
                )

                break

        if duplicate_found:
            continue

        seen_links.add(item["link"])

        unique_items.append(item)

    return unique_items


def main():

    # Leer configuración
    with open(
        CONFIG_FILE,
        "r",
        encoding="utf-8"
    ) as file:

        config = json.load(file)

    all_items = []

    # --------------------------------
    # DESCARGAR TODAS LAS FUENTES
    # --------------------------------

    for feed in config["feeds"]:

        try:

            print(
                f"\nLeyendo: {feed['name']}"
            )

            xml_data = download_feed(
                feed["url"]
            )

            items = parse_feed(
                xml_data,
                feed["name"]
            )

            all_items.extend(items)

            print(
                f"Noticias encontradas: {len(items)}"
            )

        except Exception as error:

            print(
                f"ERROR en {feed['name']}: {error}"
            )

    print(
        f"\nTotal antes de duplicados: {len(all_items)}"
    )

    # --------------------------------
    # ELIMINAR DUPLICADOS
    # --------------------------------

    unique_items = remove_duplicates(
        all_items
    )

    print(
        f"Total después de duplicados: {len(unique_items)}"
    )

    # --------------------------------
    # LIMITAR RESULTADOS
    # --------------------------------

    unique_items = unique_items[:MAX_ITEMS]

    # --------------------------------
    # CREAR RSS
    # --------------------------------

    rss = ET.Element(
        "rss",
        {
            "version": "2.0",
            "xmlns:atom":
                "http://www.w3.org/2005/Atom"
        }
    )

    channel = ET.SubElement(
        rss,
        "channel"
    )

    ET.SubElement(
        channel,
        "title"
    ).text = (
        "G6 Austral — Últimas Noticias"
    )

    ET.SubElement(
        channel,
        "link"
    ).text = (
        "https://gorilasixcl-maker.github.io/"
        "g6austral-rss/"
    )

    ET.SubElement(
        channel,
        "description"
    ).text = (
        "Noticias de Chile, defensa, "
        "seguridad e internacional "
        "seleccionadas por G6 Austral."
    )

    ET.SubElement(
        channel,
        "language"
    ).text = "es-CL"

    ET.SubElement(
        channel,
        "lastBuildDate"
    ).text = datetime.now(
        timezone.utc
    ).strftime(
        "%a, %d %b %Y %H:%M:%S +0000"
    )

    # --------------------------------
    # AGREGAR NOTICIAS
    # --------------------------------

    for item in unique_items:

        rss_item = ET.SubElement(
            channel,
            "item"
        )

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

    # --------------------------------
    # GUARDAR
    # --------------------------------

    tree = ET.ElementTree(rss)

    ET.indent(
        tree,
        space="  "
    )

    tree.write(
        OUTPUT_FILE,
        encoding="utf-8",
        xml_declaration=True
    )

    print(
        f"\nRSS creado correctamente: "
        f"{OUTPUT_FILE}"
    )

    print(
        f"Noticias finales: "
        f"{len(unique_items)}"
    )


if __name__ == "__main__":
    main()
