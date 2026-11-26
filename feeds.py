import json
import re
import html
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.parse import urljoin
from email.utils import parsedate_to_datetime
from difflib import SequenceMatcher

CONFIG_FILE = "feeds.json"
OUTPUT_FILE = "feed.xml"

MAX_ITEMS = 100

# Mientras más alto, más estricta es la detección.
DUPLICATE_THRESHOLD = 0.82

# Tiempo máximo para intentar obtener una imagen
IMAGE_TIMEOUT = 10

MEDIA_NS = "http://search.yahoo.com/mrss/"


# =========================================================
# DESCARGAR URL
# =========================================================

def download_url(url, timeout=30):

    request = Request(
        url,
        headers={
            "User-Agent":
                "Mozilla/5.0 (compatible; G6-Austral-RSS/1.0)"
        }
    )

    with urlopen(
        request,
        timeout=timeout
    ) as response:

        return response.read()


# =========================================================
# FECHA
# =========================================================

def parse_date(value):

    if not value:
        return datetime.now(timezone.utc)

    try:

        return parsedate_to_datetime(
            value
        ).astimezone(timezone.utc)

    except Exception:

        return datetime.now(timezone.utc)


# =========================================================
# LIMPIAR TEXTO
# =========================================================

def clean_text(text):

    if not text:
        return ""

    text = html.unescape(text)

    text = re.sub(
        r"<[^>]+>",
        " ",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# =========================================================
# NORMALIZAR TITULAR
# =========================================================

def normalize_title(title):

    title = clean_text(
        title
    ).lower()

    title = re.sub(
        r"[^\w\sáéíóúüñ]",
        " ",
        title
    )

    title = re.sub(
        r"\s+",
        " ",
        title
    ).strip()

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


# =========================================================
# DETECTAR DUPLICADOS
# =========================================================

def titles_are_duplicate(
    title_a,
    title_b
):

    normalized_a = normalize_title(
        title_a
    )

    normalized_b = normalize_title(
        title_b
    )

    if not normalized_a or not normalized_b:
        return False

    if normalized_a == normalized_b:
        return True

    similarity = SequenceMatcher(
        None,
        normalized_a,
        normalized_b
    ).ratio()

    return similarity >= DUPLICATE_THRESHOLD


# =========================================================
# BUSCAR IMAGEN EN HTML
# =========================================================

def extract_image_from_html(
    html_data,
    base_url=""
):

    if not html_data:
        return ""

    # -----------------------------------------------------
    # 1. og:image
    # -----------------------------------------------------

    patterns = [

        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',

        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',

        r'<meta[^>]+property=["\']og:image:url["\'][^>]+content=["\']([^"\']+)["\']',

        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image:url["\']',

    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            html_data,
            re.IGNORECASE
        )

        if match:

            image_url = (
                match.group(1)
                .strip()
            )

            return urljoin(
                base_url,
                image_url
            )


    # -----------------------------------------------------
    # 2. twitter:image
    # -----------------------------------------------------

    patterns = [

        r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',

        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\']',

    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            html_data,
            re.IGNORECASE
        )

        if match:

            image_url = (
                match.group(1)
                .strip()
            )

            return urljoin(
                base_url,
                image_url
            )


    # -----------------------------------------------------
    # 3. Imagen dentro del contenido
    # -----------------------------------------------------

    patterns = [

        r'<img[^>]+src=["\']([^"\']+)["\']',

        r'<img[^>]+data-src=["\']([^"\']+)["\']',

        r'<img[^>]+data-lazy-src=["\']([^"\']+)["\']',

    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            html_data,
            re.IGNORECASE
        )

        if match:

            image_url = (
                match.group(1)
                .strip()
            )

            if image_url.startswith(
                (
                    "http://",
                    "https://"
                )
            ):

                return image_url

            return urljoin(
                base_url,
                image_url
            )

    return ""


# =========================================================
# OBTENER IMAGEN DESDE LA NOTICIA
# =========================================================

def fetch_article_image(
    article_url
):

    if not article_url:
        return ""

    try:

        html_data = download_url(
            article_url,
            timeout=IMAGE_TIMEOUT
        ).decode(
            "utf-8",
            errors="ignore"
        )

        return extract_image_from_html(
            html_data,
            article_url
        )

    except Exception as error:

        print(
            f"  No se pudo obtener imagen: {error}"
        )

        return ""


# =========================================================
# EXTRAER IMAGEN DEL ITEM RSS
# =========================================================

def extract_image(
    item,
    description="",
    link=""
):

    # -----------------------------------------------------
    # 1. media:content
    # -----------------------------------------------------

    media_content = item.find(
        f"{{{MEDIA_NS}}}content"
    )

    if media_content is not None:

        url = media_content.attrib.get(
            "url",
            ""
        )

        if url:

            return url


    # -----------------------------------------------------
    # 2. media:thumbnail
    # -----------------------------------------------------

    media_thumbnail = item.find(
        f"{{{MEDIA_NS}}}thumbnail"
    )

    if media_thumbnail is not None:

        url = media_thumbnail.attrib.get(
            "url",
            ""
        )

        if url:

            return url


    # -----------------------------------------------------
    # 3. enclosure
    # -----------------------------------------------------

    enclosure = item.find(
        "enclosure"
    )

    if enclosure is not None:

        url = enclosure.attrib.get(
            "url",
            ""
        )

        mime_type = enclosure.attrib.get(
            "type",
            ""
        ).lower()

        if url and (
            mime_type.startswith(
                "image/"
            )
            or re.search(
                r"\.(jpg|jpeg|png|webp|gif)(\?.*)?$",
                url,
                re.IGNORECASE
            )
        ):

            return url


    # -----------------------------------------------------
    # 4. imagen dentro del description
    # -----------------------------------------------------

    image = extract_image_from_html(
        description,
        link
    )

    if image:
        return image


    # -----------------------------------------------------
    # 5. intentar página original
    # -----------------------------------------------------

    if link:

        print(
            f"  Buscando imagen: {link}"
        )

        image = fetch_article_image(
            link
        )

        if image:
            return image

    return ""


# =========================================================
# PARSEAR RSS / ATOM
# =========================================================

def parse_feed(
    xml_data,
    source_name
):

    root = ET.fromstring(
        xml_data
    )

    items = []


    # =====================================================
    # RSS
    # =====================================================

    for item in root.findall(
        ".//item"
    ):

        title = item.findtext(
            "title",
            ""
        ).strip()

        link = item.findtext(
            "link",
            ""
        ).strip()

        description = item.findtext(
            "description",
            ""
        ).strip()

        pub_date = item.findtext(
            "pubDate",
            ""
        ).strip()


        if title and link:

            image = extract_image(
                item,
                description,
                link
            )


            items.append({

                "title":
                    clean_text(title),

                "link":
                    link,

                "description":
                    clean_text(description),

                "date":
                    parse_date(pub_date),

                "source":
                    source_name,

                "image":
                    image

            })


    # =====================================================
    # ATOM
    # =====================================================

    namespace = (
        "{http://www.w3.org/2005/Atom}"
    )


    for entry in root.findall(
        f".//{namespace}entry"
    ):

        title_element = entry.find(
            f"{namespace}title"
        )

        title = (
            title_element.text.strip()
            if title_element is not None
            and title_element.text
            else ""
        )


        link = ""

        for link_element in entry.findall(
            f"{namespace}link"
        ):

            href = link_element.attrib.get(
                "href"
            )

            if href:

                link = href

                break


        summary_element = entry.find(
            f"{namespace}summary"
        )

        description = (
            summary_element.text.strip()
            if summary_element is not None
            and summary_element.text
            else ""
        )


        content_element = entry.find(
            f"{namespace}content"
        )

        if (
            not description
            and content_element is not None
            and content_element.text
        ):

            description = (
                content_element.text.strip()
            )


        updated_element = entry.find(
            f"{namespace}updated"
        )

        updated = (
            updated_element.text.strip()
            if updated_element is not None
            and updated_element.text
            else ""
        )


        try:

            date = datetime.fromisoformat(
                updated.replace(
                    "Z",
                    "+00:00"
                )
            )

        except Exception:

            date = datetime.now(
                timezone.utc
            )


        if title and link:

            image = extract_image_from_html(
                description,
                link
            )


            if not image:

                image = fetch_article_image(
                    link
                )


            items.append({

                "title":
                    clean_text(title),

                "link":
                    link,

                "description":
                    clean_text(description),

                "date":
                    date,

                "source":
                    source_name,

                "image":
                    image

            })


    return items


# =========================================================
# ELIMINAR DUPLICADOS
# =========================================================

def remove_duplicates(
    items
):

    items.sort(
        key=lambda item: item["date"],
        reverse=True
    )

    unique_items = []

    seen_links = set()


    for item in items:

        # -------------------------------------------------
        # URL EXACTAMENTE IGUAL
        # -------------------------------------------------

        if item["link"] in seen_links:
            continue


        # -------------------------------------------------
        # TITULARES SIMILARES
        # -------------------------------------------------

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


        seen_links.add(
            item["link"]
        )

        unique_items.append(
            item
        )


    return unique_items


# =========================================================
# MAIN
# =========================================================

def main():

    # -----------------------------------------------------
    # LEER CONFIGURACIÓN
    # -----------------------------------------------------

    with open(
        CONFIG_FILE,
        "r",
        encoding="utf-8"
    ) as file:

        config = json.load(
            file
        )


    all_items = []


    # -----------------------------------------------------
    # DESCARGAR FUENTES
    # -----------------------------------------------------

    for feed in config["feeds"]:

        try:

            print(
                f"\nLeyendo: {feed['name']}"
            )


            xml_data = download_url(
                feed["url"]
            )


            items = parse_feed(
                xml_data,
                feed["name"]
            )


            all_items.extend(
                items
            )


            print(
                f"Noticias encontradas: {len(items)}"
            )


        except Exception as error:

            print(
                f"ERROR en {feed['name']}: {error}"
            )


    print(
        f"\nTotal antes de duplicados: "
        f"{len(all_items)}"
    )


    # -----------------------------------------------------
    # DUPLICADOS
    # -----------------------------------------------------

    unique_items = remove_duplicates(
        all_items
    )


    print(
        f"Total después de duplicados: "
        f"{len(unique_items)}"
    )


    # -----------------------------------------------------
    # LIMITAR
    # -----------------------------------------------------

    unique_items = unique_items[
        :MAX_ITEMS
    ]


    # =====================================================
    # CREAR RSS
    # =====================================================

    rss = ET.Element(
        "rss",
        {
            "version": "2.0",
            "xmlns:atom":
                "http://www.w3.org/2005/Atom",
            "xmlns:media":
                MEDIA_NS
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


    # =====================================================
    # AGREGAR NOTICIAS
    # =====================================================

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


        # -------------------------------------------------
        # IMAGEN
        # -------------------------------------------------

        if item.get("image"):

            ET.SubElement(
                rss_item,
                f"{{{MEDIA_NS}}}content",
                {
                    "url":
                        item["image"],

                    "medium":
                        "image"
                }
            )


    # =====================================================
    # GUARDAR
    # =====================================================

    tree = ET.ElementTree(
        rss
    )


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
