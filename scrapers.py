# -*- coding: utf-8 -*-
"""
Urban Lex Tracker — Scrapers Module
8 bots de rastreo: Diario Oficial, Contraloría, MINVU, BCN,
Poder Judicial, Prensa, Proyectos de Ley, IPT.
"""

import os
import re
import requests
import urllib3
import warnings
import feedparser
import markdown
import pytz
from datetime import datetime
from bs4 import BeautifulSoup
from dotenv import load_dotenv

import database

# Suppress unverified HTTPS warnings globally
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings("ignore", category=urllib3.exceptions.InsecureRequestWarning)
warnings.simplefilter("ignore", urllib3.exceptions.InsecureRequestWarning)

load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY", "")
CHILE_TZ = pytz.timezone("America/Santiago")
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
TIMEOUT = 20


URBANISM_KEYWORDS = [
    "urbanismo", "urbanístico", "urbanística", "urbano", "urbana",
    "arquitectura", "construcción inmobiliaria", "inmobiliario", "inmobiliaria",
    "loteo", "subdivisión", "plan regulador", "plan intercomunal",
    "planificación urbana", "gestión urbana", "permiso de edificación",
    "recepción definitiva", "dirección de obras municipales",
    "minvu", "seremi de vivienda",
    "subsidio habitacional", "vivienda social",
    "bienes nacionales", "expropiación",
    "ley general de urbanismo", "ordenanza general",
    "oguc", "lguc",
    "evaluación de impacto ambiental", "seia",
    "uso de suelo", "zona rural", "área verde",
    "condominio", "copropiedad",
    "campamento", "asentamiento irregular",
    "obras públicas viales", "borde costero",
    "patrimonio arquitectónico", "monumento nacional", "zona típica",
    "edificación", "ddu", "circular ddu",
    "empresa constructora", "empresa inmobiliaria",
    "derecho urbanístico", "litigio urbanístico",
    "mercado inmobiliario", "precio del suelo",
    "densificación", "renovación urbana", "plusvalía",
    "plataforma urbana", "cámara chilena de la construcción",
    "cchc", "bim", "permisos de obra",
]

def is_urban_topic(texto: str) -> bool:
    if not texto or len(texto) < 5:
        return False
    texto_low = texto.lower()
    return any(kw in texto_low for kw in URBANISM_KEYWORDS)


def is_item_valid(texto: str) -> bool:
    if not texto or len(texto.strip()) < 10:
        return False

    texto_low = texto.lower()

    # 1. Filtro Estricto: Tiene que ser de Urbanismo
    if not is_urban_topic(texto):
        return False

    # 2. Ignorar palabras de navegación o temas no urbanísticos
    if any(
        w in texto_low
        for w in [
            "inicio",
            "volver",
            "buscar",
            "contacto",
            "menú",
            "menu",
            "faq",
            "sitio",
            "portal",
            "navegar",
            "kerosene",
            "combustible",
            "impuesto específico",
            "petróleo",
            "paridad",
            "educación",
            "salud",
            "extradición",
            "armas",
            "pesca",
            "acuicultura",
            "fuerzas armadas",
            "ejército",
            "armada",
            "fuerza aérea",
            "carabineros",
            "pdi",
            "policía",
            "cárcel",
            "gendarmería",
            "hospital",
            "cenabast",
            "isp",
            "diplomático",
            "embajador",
            "consulado",
            "nombramiento",
            "renuncia",
            "asciende",
            "pensión",
            "jubilación",
            "aguinaldo",
        ]
    ):
        return False

    now = datetime.now(pytz.timezone("America/Santiago"))

    # 3. Excluir títulos de navegación estáticos del Minvu (que siempre están en la web pero no son noticias)
    if re.search(
        r"^(ley sobre agilización|ley de aportes|circulares de la|circulares división|normas técnicas)\b",
        texto_low,
    ):
        return False

    # 4. Evitar años pasados (si menciona años viejos explícitamente y no el actual)
    prev_years = [
        str(now.year - i) for i in range(1, 40)
    ]  # Expandir hasta 40 años atrás
    pattern = r"\b(" + "|".join(prev_years) + r")\b"
    # Si menciona el año pasado pero TAMBIEN el actual, lo pasamos. Si SOLO menciona año pasado, false.
    if re.search(pattern, texto) and str(now.year) not in texto:
        return False

    # Evitar DDUs o resoluciones con sufijo de año muy antiguo (ej: DDU-ESP 001-07)
    # Buscar patrones como "-07" "-15" "-2015"
    old_suffix_years = [
        f"-{str(now.year - i)[-2:]}" for i in range(2, 40)
    ]  # -07, -15, etc (dejamos 1 año de gracia)
    old_suffix_years += [f"-{now.year - i}" for i in range(2, 40)]  # -2007, -2015, etc

    # Excepción rápida para DDU antiguas en formato DDU-ESP NNN-YY o NNN-YYYY
    ddu_match = re.search(r"DDU.*?-(\d{2,4})\b", texto, re.IGNORECASE)
    if ddu_match:
        year_str = ddu_match.group(1)
        if len(year_str) == 2:
            # asume 2000s
            y = int("20" + year_str)
            if y < now.year - 1:  # Si es más antiguo que el año pasado, descartar
                return False
        elif len(year_str) == 4:
            y = int(year_str)
            if y < now.year - 1:
                return False
        elif len(year_str) == 4:
            y = int(year_str)
            if y < now.year - 1:
                return False

    # 5. Requerimos algún identificador normativo o keyword de acción
    if not re.search(r"\d+", texto):
        if not re.search(
            r"(consulta ciudadana|participación|proyecto de|norma|actualiza|ley|decreto|resolución|oficio|dictamen|aprueba|rechaza)",
            texto_low,
        ):
            return False

    return True

    # Evitar años pasados explícitos del 2015 al año pasado
    prev_years = [str(now.year - i) for i in range(1, 15)]
    pattern = r"\b(" + "|".join(prev_years) + r")\b"
    if re.search(pattern, texto):
        return False

    # Requerimos que la normativa tenga al menos ALGÚN DATO numérico o identificador.
    # Ej: "Ley 21.442", "Resolución 45", "DDU 460". Si sólo son letras ("Ley de algo"), suele ser menú genérico.
    if not re.search(r"\d+", texto):
        if not re.search(
            r"(consulta\sciudadana|participación|proyecto\sde\s|norma\s|actualiza)",
            texto_low,
        ):
            return False

    if re.search(
        r"(n°|núm|nro|modifica|promulga|fallo|rol|sentencia|proyecto|boletín|ordinario|decreto|resolución|circular|ddu)\s*\d+",
        texto,
        re.IGNORECASE,
    ):
        return True

    if len(texto) < 20:
        return False

    return True


def is_feed_today(entry) -> bool:
    if not hasattr(entry, "published_parsed") or not entry.published_parsed:
        return True
    now = datetime.now(pytz.timezone("America/Santiago"))
    return (
        entry.published_parsed.tm_year == now.year
        and entry.published_parsed.tm_mon == now.month
        and entry.published_parsed.tm_mday == now.day
    )


def is_spanish_date_today(date_str: str) -> bool:
    if not date_str:
        return False

    month_map = {
        "enero": 1,
        "febrero": 2,
        "marzo": 3,
        "abril": 4,
        "mayo": 5,
        "junio": 6,
        "julio": 7,
        "agosto": 8,
        "septiembre": 9,
        "octubre": 10,
        "noviembre": 11,
        "diciembre": 12,
    }

    # Format: "DD de MM de YYYY"
    match = re.search(r"(\d{1,2})\s+de\s+([a-zA-Z]+)\s+de\s+(\d{4})", date_str.lower())
    if match:
        day, month_name, year = match.groups()
        month = month_map.get(month_name)
        if not month:
            return False

        try:
            date_obj = datetime(int(year), month, int(day))
            now = datetime.now(CHILE_TZ)
            return (
                date_obj.year == now.year
                and date_obj.month == now.month
                and date_obj.day == now.day
            )
        except ValueError:
            return False

    # Format: "YYYY-MM-DD"
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})", date_str)
    if match:
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            now = datetime.now(CHILE_TZ)
            return (
                date_obj.year == now.year
                and date_obj.month == now.month
                and date_obj.day == now.day
            )
        except ValueError:
            return False

    return False


def hoy_chile():
    now = datetime.now(CHILE_TZ)
    meses = [
        "",
        "enero",
        "febrero",
        "marzo",
        "abril",
        "mayo",
        "junio",
        "julio",
        "agosto",
        "septiembre",
        "octubre",
        "noviembre",
        "diciembre",
    ]
    return f"{now.day} de {meses[now.month]} de {now.year}"


def call_gemini(prompt: str) -> str:
    if not API_KEY:
        return "⚠️ API Key de Gemini no configurada."
    try:
        # Cambiamos a v1 estable para evitar errores de modelo no encontrado
        url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={API_KEY}"
        resp = requests.post(
            url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=60
        )
        data = resp.json()
        if "candidates" in data and data["candidates"]:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        return f"Sin respuesta de Gemini: {data}"
    except Exception as e:
        return f"Error llamando a Gemini: {e}"


def _get_db_history(source: str, limit: int = 3) -> list:
    """Obtiene los últimos registros de la fuente desde la BD."""
    try:
        conn = database.get_connection()
        rows = conn.execute(
            "SELECT title, url FROM alerts WHERE source = ? ORDER BY created_at DESC LIMIT ?",
            (source, limit),
        ).fetchall()
        conn.close()
        return [{"title": r["title"], "url": r["url"]} for r in rows]
    except Exception:
        return []


def procesar_salida(source, items_nuevos, icon, title, limit_history=3):
    """Lógica unificada para garantizar que si no hay novedad, se diga en Python y no dependa de Gemini."""

    fecha_str = hoy_chile()

    # 1. Preparar bloque del día
    if items_nuevos:
        texto_extraido = "\n".join(items_nuevos[:8])
        prompt = f"""Eres experto normativo en urbanismo y arquitectura chilena. Fecha: {fecha_str}.
        Redacta un informe Markdown sobre estos NUEVOS hallazgos relevantes para empresas constructoras, inmobiliarias y arquitectos.
        Usa viñetas para cada hallazgo destacando el impacto brevemente.
        Hallazgos:
        {texto_extraido}"""
        bloque_hoy = call_gemini(prompt)
        bloque_hoy = (
            f"**{icon} {title}**\n\n✅ **Novedades de Hoy ({fecha_str}):** Se han detectado **{len(items_nuevos)}** nuevos hallazgos en el ámbito urbano, arquitectónico e inmobiliario.\n\n"
            + bloque_hoy
        )
    else:
        bloque_hoy = f"**{icon} {title}**\n\n📌 **Novedades de Hoy ({fecha_str}):** 0 hallazgos.\n*(No se han detectado nuevas leyes, decretos u ordenanzas de relevancia urbanística o arquitectónica el día de hoy).* \n\n"

    # 2. Preparar bloque histórico
    historicos = _get_db_history(source, limit_history)
    if not historicos:
        bloque_hist = "**Historial Reciente:**\n- La base de datos histórica de esta fuente se encuentra vacía."
    else:
        texto_hist = "\n".join(
            [f"- **[{h['title']}]({h['url']})**" for h in historicos]
        )
        prompt_hist = f"""Eres experto normativo. Toma esta lista de items históricos de normativas de arquitectura y urbanismo, y formatea UNA breve viñeta por item explicando de qué trata (muy conciso, para arquitectos y constructoras). Formato Markdown.
        Items Históricos:
        {texto_hist}"""
        gemini_hist = call_gemini(prompt_hist)
        bloque_hist = "**Historial Reciente:**\n\n" + gemini_hist

    # 3. Ensamblar separados por línea
    out = f"{bloque_hoy}\n\n---\n\n{bloque_hist}"
    return out


# ════════════════════════════════════════════════════════════════
# BOT 1: DIARIO OFICIAL
# ════════════════════════════════════════════════════════════════


def scrape_diario_oficial() -> dict:
    source = "diario-oficial"
    items = []
    try:
        url = "https://www.diariooficial.interior.gob.cl/edicionelectronica/"
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, verify=False)
        soup = BeautifulSoup(r.text, "html.parser")

        # Estrategia: Buscar todos los links PDF y subir al contenedor para hallar títulos
        # En el DO, las normas suelen estar en una estructura de tabla o div con texto descriptivo
        for a in soup.find_all("a", href=re.compile(r"\.pdf$")):
            link = a.get("href", "")
            full_link = (
                link
                if link.startswith("http")
                else "https://www.diariooficial.interior.gob.cl" + link
            )

            # Buscamos el texto descriptivo. Suele estar en el TD anterior o en el mismo contenedor
            # Intentamos obtener el texto del abuelo o del padre
            container = a.find_parent("tr") or a.find_parent("div")
            if container:
                title = container.get_text().strip()
                # Limpiar texto de "Ver PDF" y ruidos de CVE
                title = re.sub(
                    r"Ver PDF\s*\(CVE-\d+\)", "", title, flags=re.IGNORECASE
                ).strip()
                title = re.sub(r"\s+", " ", title)  # Colapsar espacios
            else:
                title = a.get_text().strip()

            if not title or len(title) < 15:
                continue

            if is_item_valid(title):
                # Try to extract actual publication date from URL
                pub_date = hoy_chile()
                date_match = re.search(r"/(\d{4})/(\d{2})/(\d{2})/", full_link)
                if date_match:
                    pub_date = f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}"

                is_new = database.save_alert(
                    source=source,
                    title=title[:300],
                    url=full_link,
                    category="normativa",
                    date=pub_date,
                )
                if is_new:
                    items.append(f"DO: {title[:150]}... | Link: {full_link}")

    except Exception as e:
        database.save_scrape_history(source, 0, "error", str(e))
        return {
            "source": source,
            "items": [],
            "count": 0,
            "report_html": f"<p>Error: {e}</p>",
        }

    informe_md = procesar_salida(source, items, "📰", "Diario Oficial")
    database.save_scrape_history(source, len(items), "success")
    return {
        "source": source,
        "items": items,
        "count": len(items),
        "report_html": markdown.markdown(informe_md),
        "report_md": informe_md,
    }


# ════════════════════════════════════════════════════════════════
# BOT 2: CONTRALORÍA
# ════════════════════════════════════════════════════════════════


def scrape_contraloria() -> dict:
    source = "contraloria"
    items = []
    try:
        # Página de jurisprudencia reciente
        url = "https://www.contraloria.cl/web/cgr/buscar-jurisprudencia"
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        soup = BeautifulSoup(r.text, "html.parser")

        # Buscamos links que parezcan dictámenes o resoluciones
        for a in soup.find_all("a"):
            texto = a.get_text().strip()
            link = a.get("href", "")
            if not link:
                continue

            if is_item_valid(texto):
                full_link = (
                    "https://www.contraloria.cl" + link
                    if link.startswith("/")
                    else link
                )
                is_new = database.save_alert(
                    source=source,
                    title=texto,
                    url=full_link,
                    category="dictamen",
                    date=hoy_chile(),
                )
                if is_new:
                    items.append(f"CGR: {texto}")
    except Exception as e:
        database.save_scrape_history(source, 0, "error", f"Error: {e}")

    informe_md = procesar_salida(source, items, "🏛️", "Contraloría General")
    database.save_scrape_history(source, len(items), "success")
    return {
        "source": source,
        "items": items,
        "count": len(items),
        "report_html": markdown.markdown(informe_md),
        "report_md": informe_md,
    }


# ════════════════════════════════════════════════════════════════
# BOT 3: MINVU (DDU & Normas)
# ════════════════════════════════════════════════════════════════
def scrape_minvu() -> dict:
    source = "minvu"
    items = []
    today_iso = datetime.now(CHILE_TZ).strftime("%Y-%m-%d")
    current_year = str(datetime.now(CHILE_TZ).year)

    try:
        urls = [
            "https://www.minvu.gob.cl/elementos-tecnicos/circulares-division-de-desarrollo-urbano-ddu/circulares-generales-por-numero/",
            "https://www.minvu.gob.cl/elementos-tecnicos/circulares-division-de-desarrollo-urbano-ddu/circulares-especificas-ddu-por-numero/",
            "https://www.minvu.gob.cl/noticias/noticias/",
        ]
        for url in urls:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, verify=False)
            soup = BeautifulSoup(r.text, "html.parser")

            found_in_url = 0
            for a in soup.find_all("a"):
                if found_in_url >= 50:
                    break

                href = a.get("href", "")
                texto = a.get_text(separator=" ").strip()
                texto = re.sub(r"\s+", " ", texto)

                if not is_item_valid(texto) or len(texto) <= 10:
                    continue

                # Extraer año del texto o URL
                year_in_text = re.search(r"\b(202[4-9])\b", texto)
                year_in_url  = re.search(r"/(202[4-9])/", href)
                is_recent = bool(year_in_text or year_in_url)

                # Extraer fecha completa si existe
                date_found = None
                for match in re.finditer(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", texto):
                    d, m, y = match.groups()
                    if y >= "2024":
                        date_found = f"{y}-{m.zfill(2)}-{d.zfill(2)}"
                        break

                # Si no hay año reciente ni en texto ni en URL → descartar
                if not is_recent and not date_found:
                    continue

                # Blacklist de DDUs históricas conocidas
                blacklist = ["DDU-ESP 043", "DDU-ESP 061", "DDU-ESP 006", "DDU-ESP 015"]
                if any(b in texto for b in blacklist):
                    continue

                link = href
                if link and link.startswith("/"):
                    link = "https://www.minvu.gob.cl" + link

                if not ("minvu.gob.cl" in link.lower() or "ddu" in texto.lower()):
                    continue

                item_date = date_found if date_found else today_iso
                is_today  = (date_found == today_iso) or is_spanish_date_today(texto)

                found_in_url += 1
                is_new = database.save_alert(
                    source=source,
                    title=texto[:300],
                    url=link,
                    category="norma_tecnica",
                    date=item_date,
                )
                if is_new and is_today:
                    items.append(f"MINVU: {texto[:150]}")

    except Exception as e:
        database.save_scrape_history(source, 0, "error", str(e))
        return {
            "source": source,
            "items": [],
            "count": 0,
            "report_html": f"<p>Error: {e}</p>",
        }

    informe_md = procesar_salida(source, items, "🏢", "MINVU")
    database.save_scrape_history(source, len(items), "success")
    return {
        "source": source,
        "items": items,
        "count": len(items),
        "report_html": markdown.markdown(informe_md),
        "report_md": informe_md,
    }

# ════════════════════════════════════════════════════════════════
# BOT 4: BCN → CAMARA PRENSA
# ════════════════════════════════════════════════════════════════
def scrape_bcn() -> dict:
    source = "bcn"
    items = []
    try:
        url = "https://www.camara.cl/prensa/prensa_cms.aspx"
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.find_all("a", href=re.compile(r"\.(aspx|html|htm)", re.I)):
            texto = a.get_text().strip()
            link = a.get("href", "")
            if not texto or len(texto) < 10:
                continue
            if not is_urban_topic(texto):
                continue
            full_link = (
                "https://www.camara.cl" + link
                if link.startswith("/")
                else link
            )
            is_new = database.save_alert(
                source=source,
                title=texto,
                url=full_link,
                category="legislacion",
                date=hoy_chile(),
            )
            if is_new:
                items.append(f"Cámara Prensa: {texto}")
    except Exception as e:
        pass
    informe_md = procesar_salida(source, items, "📚", "Cámara de Diputadas y Diputados")
    database.save_scrape_history(source, len(items), "success")
    return {
        "source": source,
        "items": items,
        "count": len(items),
        "report_html": markdown.markdown(informe_md),
        "report_md": informe_md,
    }


# ════════════════════════════════════════════════════════════════
# BOT 5: PODER JUDICIAL
# ════════════════════════════════════════════════════════════════


def scrape_poder_judicial() -> dict:
    source = "poder-judicial"
    items = []
    try:
        # Portal de noticias actualizado
        url = "https://www.pjud.cl/prensa-y-comunicaciones/noticias-del-poder-judicial"
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        soup = BeautifulSoup(r.text, "html.parser")

        # Buscamos los items de resultados de noticias
        for item in soup.find_all(class_="jt-result-item"):
            a = item.find("a")
            if not a:
                continue

            texto = a.get_text().strip()
            if is_item_valid(texto):
                link = (
                    "https://www.pjud.cl" + a.get("href", "")
                    if a.get("href", "").startswith("/")
                    else a.get("href", url)
                )
                is_new = database.save_alert(
                    source=source,
                    title=texto,
                    url=link,
                    category="jurisprudencia",
                    date=hoy_chile(),
                )
                if is_new:
                    items.append(f"PJUD: {texto}")
    except Exception as e:
        pass

    informe_md = procesar_salida(source, items, "⚖️", "Poder Judicial")
    database.save_scrape_history(source, len(items), "success")
    return {
        "source": source,
        "items": items,
        "count": len(items),
        "report_html": markdown.markdown(informe_md),
        "report_md": informe_md,
    }


# ════════════════════════════════════════════════════════════════
# BOT 6: PRENSA
# ════════════════════════════════════════════════════════════════


def scrape_prensa() -> dict:
    source = "prensa"
    items = []
    rss_feeds = [
        "https://www.emol.com/rss_html/ultimas_noticias.xml",
        "https://www.latercera.com/rss/",
    ]
    for rss_url in rss_feeds:
        try:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries[:20]:
                title = entry.get("title", "").strip()
                link = entry.get("link", "")
                if is_urban_topic(title):
                    if is_feed_today(entry):
                        is_new = database.save_alert(
                            source=source,
                            title=title,
                            url=link,
                            category="prensa",
                            date=hoy_chile(),
                        )
                        if is_new:
                            items.append(f"PRENSA: {title} | Link: {link}")
        except:
            continue

    informe_md = procesar_salida(source, items, "🗞️", "Noticias de Prensa")
    database.save_scrape_history(source, len(items), "success")
    return {
        "source": source,
        "items": items,
        "count": len(items),
        "report_html": markdown.markdown(informe_md),
        "report_md": informe_md,
    }


# ════════════════════════════════════════════════════════════════
# BOT 7: PROYECTOS DE LEY
# ════════════════════════════════════════════════════════════════


def scrape_proyectos_ley() -> dict:
    source = "proyectos-ley"
    items = []
    try:
        # Página de proyectos de ley actualizada
        url = "https://www.camara.cl/legislacion/ProyectosDeLey/proyectos_ley.aspx"
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        soup = BeautifulSoup(r.text, "html.parser")

        # Buscamos en las tablas de proyectos recientes
        for tag in soup.find_all("a", href=re.compile(r"prmID=")):
            texto = tag.get_text().strip()
            if is_item_valid(texto):
                link = "https://www.camara.cl/legislacion/ProyectosDeLey/" + tag.get(
                    "href"
                )
                is_new = database.save_alert(
                    source=source,
                    title=texto,
                    url=link,
                    category="proyecto_ley",
                    date=hoy_chile(),
                )
                if is_new:
                    items.append(f"Cámara: {texto}")
    except Exception as e:
        pass

    informe_md = procesar_salida(source, items, "🏛️", "Proyectos de Ley")
    database.save_scrape_history(source, len(items), "success")
    return {
        "source": source,
        "items": items,
        "count": len(items),
        "report_html": markdown.markdown(informe_md),
        "report_md": informe_md,
    }


# ════════════════════════════════════════════════════════════════
# BOT 8: IPT
# ════════════════════════════════════════════════════════════════


def scrape_ipt() -> dict:
    source = "ipt"
    items = []
    try:
        # Usamos el portal de estudios del MINVU como alternativa robusta para IPT
        url = "https://centrodeestudios.minvu.gob.cl/"
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        soup = BeautifulSoup(r.text, "html.parser")

        for tag in soup.find_all("a"):
            texto = tag.get_text().strip()
            if is_item_valid(texto):
                link = tag.get("href", "")
                full_link = link if link.startswith("http") else url + link
                is_new = database.save_alert(
                    source=source,
                    title=texto,
                    url=full_link,
                    category="ipt",
                    date=hoy_chile(),
                )
                if is_new:
                    items.append(f"IPT/MINVU: {texto}")
    except:
        pass

    informe_md = procesar_salida(source, items, "🗺️", "Instrumentos de Planificación")
    database.save_scrape_history(source, len(items), "success")
    return {
        "source": source,
        "items": items,
        "count": len(items),
        "report_html": markdown.markdown(informe_md),
        "report_md": informe_md,
    }


# BOT 9: SEA (Servicio de Evaluación Ambiental)
# ════════════════════════════════════════════════════════════════


def scrape_sea() -> dict:
    source = "sea"
    items = []
    try:
        # Portal de noticias del SEA
        url = "https://www.sea.gob.cl/noticias"
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, verify=False)
        soup = BeautifulSoup(r.text, "html.parser")

        # En el portal de noticias del SEA, buscamos títulos y links en las filas de vistas
        for article in soup.find_all("div", class_="views-row"):
            link_tag = article.find("a")
            if not link_tag:
                continue

            title = link_tag.get_text().strip()
            link = link_tag.get("href", "")

            if is_item_valid(title):
                full_link = (
                    link if link.startswith("http") else "https://www.sea.gob.cl" + link
                )
                is_new = database.save_alert(
                    source=source,
                    title=title[:250],
                    url=full_link,
                    category="ambiental",
                    date=hoy_chile(),
                )
                if is_new:
                    items.append(f"SEA: {title} | Link: {full_link}")

    except Exception as e:
        database.save_scrape_history(source, 0, "error", str(e))
        return {
            "source": source,
            "items": [],
            "count": 0,
            "report_html": f"<p>Error: {e}</p>",
        }

    informe_md = procesar_salida(source, items, "🌱", "Evaluación Ambiental")
    database.save_scrape_history(source, len(items), "success")
    return {
        "source": source,
        "items": items,
        "count": len(items),
        "report_html": markdown.markdown(informe_md),
    }


SCRAPERS = {
    "diario-oficial": scrape_diario_oficial,
    "contraloria": scrape_contraloria,
    "minvu": scrape_minvu,
    "bcn": scrape_bcn,
    "poder-judicial": scrape_poder_judicial,
    "prensa": scrape_prensa,
    "proyectos-ley": scrape_proyectos_ley,
    "ipt": scrape_ipt,
    "sea": scrape_sea,
}


def run_all_scrapers() -> dict:
    results = {}
    total = 0
    for name, fn in SCRAPERS.items():
        try:
            res = fn()
            results[name] = res
            total += res.get("count", 0)
        except Exception as e:
            database.save_scrape_history(name, 0, "error", str(e))
    return {
        "status": "success",
        "total_items": total,
        "sources": results,
        "date": hoy_chile(),
    }
