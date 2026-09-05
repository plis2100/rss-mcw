from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from feedgen.feed import FeedGenerator


BASE_URL = "https://www.mcw.edu"
NEWS_URL = "https://www.mcw.edu/newsroom/recent-news"
OUTPUT_FILE = Path("docs/feed.xml")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def limpiar(texto):
    return " ".join((texto or "").split()).strip()


def es_noticia(url):
    ruta = urlparse(url).path.rstrip("/").lower()
    prefijo = "/newsroom/news-articles/"

    return (
        ruta.startswith(prefijo)
        and len(ruta) > len(prefijo)
    )


def encontrar_contenedor(enlace):
    contenedor = enlace

    for _ in range(6):
        if not contenedor.parent:
            break

        contenedor = contenedor.parent
        texto = limpiar(contenedor.get_text(" ", strip=True))

        if (
            any(mes in texto for mes in [
                "Jan ", "Feb ", "Mar ", "Apr ",
                "May ", "Jun ", "Jul ", "Aug ",
                "Sep ", "Oct ", "Nov ", "Dec "
            ])
            and len(texto) < 2_500
        ):
            return contenedor

    return enlace.parent or enlace


def encontrar_fecha(contenedor):
    etiqueta_time = contenedor.find("time")

    if etiqueta_time:
        texto_fecha = (
            etiqueta_time.get("datetime")
            or etiqueta_time.get_text(" ", strip=True)
        )

        try:
            fecha = date_parser.parse(texto_fecha, fuzzy=True)

            if fecha.tzinfo is None:
                fecha = fecha.replace(tzinfo=timezone.utc)

            return fecha
        except (ValueError, TypeError, OverflowError):
            pass

    texto = limpiar(contenedor.get_text(" ", strip=True))

    try:
        fecha = date_parser.parse(
            texto,
            fuzzy=True,
            default=datetime(1970, 1, 1),
        )

        if fecha.year >= 2000:
            return fecha.replace(tzinfo=timezone.utc)

    except (ValueError, TypeError, OverflowError):
        pass

    return None


def encontrar_descripcion(contenedor, titulo):
    for elemento in contenedor.find_all(["p", "div"]):
        texto = limpiar(elemento.get_text(" ", strip=True))

        if (
            texto
            and texto != titulo
            and 40 <= len(texto) <= 800
            and titulo.lower() not in texto.lower()
        ):
            return texto

    return ""


def obtener_noticias():
    respuesta = requests.get(
        NEWS_URL,
        headers=HEADERS,
        timeout=60,
    )
    respuesta.raise_for_status()

    soup = BeautifulSoup(respuesta.text, "html.parser")
    noticias = {}

    for enlace in soup.find_all("a", href=True):
        url = urljoin(BASE_URL, enlace.get("href", ""))

        if not es_noticia(url):
            continue

        titulo = limpiar(enlace.get_text(" ", strip=True))

        if len(titulo) < 8:
            continue

        contenedor = encontrar_contenedor(enlace)
        fecha = encontrar_fecha(contenedor)
        descripcion = encontrar_descripcion(
            contenedor,
            titulo,
        )

        noticias[url] = {
            "titulo": titulo,
            "url": url,
            "fecha": fecha,
            "descripcion": descripcion,
        }

    if not noticias:
        raise RuntimeError(
            "No se encontraron noticias del Medical College "
            "of Wisconsin. La RSS anterior no será eliminada."
        )

    fecha_antigua = datetime(
        1970,
        1,
        1,
        tzinfo=timezone.utc,
    )

    resultado = sorted(
        noticias.values(),
        key=lambda noticia: noticia["fecha"] or fecha_antigua,
        reverse=True,
    )

    print(f"Noticias encontradas: {len(resultado)}")

    return resultado


def crear_rss(noticias):
    feed = FeedGenerator()

    feed.id(NEWS_URL)
    feed.title("Medical College of Wisconsin – Recent News")
    feed.description(
        "Latest news from the Medical College of Wisconsin"
    )
    feed.language("en")

    feed.link(
        href=NEWS_URL,
        rel="alternate",
    )

    feed.link(
        href=(
            "https://raw.githubusercontent.com/"
            "plis2100/rss-mcw/main/docs/feed.xml"
        ),
        rel="self",
    )

    feed.lastBuildDate(datetime.now(timezone.utc))

    for noticia in noticias[:100]:
        entrada = feed.add_entry()

        entrada.id(noticia["url"])
        entrada.title(noticia["titulo"])
        entrada.link(href=noticia["url"])

        entrada.description(
            noticia["descripcion"]
            or (
                "Read the complete article on the Medical "
                f"College of Wisconsin website: {noticia['titulo']}"
            )
        )

        if noticia["fecha"]:
            entrada.pubDate(
                format_datetime(noticia["fecha"])
            )

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    feed.rss_file(
        str(OUTPUT_FILE),
        pretty=True,
        encoding="UTF-8",
    )

    print(f"RSS creada correctamente: {OUTPUT_FILE}")


if __name__ == "__main__":
    noticias_obtenidas = obtener_noticias()
    crear_rss(noticias_obtenidas)
