#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Urban Lex Tracker — Digest de Email v1.0
Proceso diario: recopila novedades normativas, genera resumen con Claude Haiku
y las envía por email a los usuarios suscritos vía Resend.

Flujo:
1. Lee publications nuevas (is_new=True) de fuentes core (es_core=True)
2. Para cada usuario con notify_email=True: filtra según sus subscriptions
3. Genera resumen con Claude Haiku
4. Envía email HTML vía Resend
5. Registra en alerts_log
6. Marca todas las publications core nuevas como is_new=False
"""

import os
import logging
import markdown
from datetime import datetime, timezone

import resend
import anthropic
import pytz
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# ─── CONFIGURACIÓN ────────────────────────────────────────────
FROM_EMAIL    = "ULT <ult@agorarevision.cl>"    # ← cambiar si se usa otro remitente
SUBJECT_BASE  = "ULT · Novedades normativas"
HAIKU_MODEL   = "claude-haiku-4-5-20251001"
CHILE_TZ      = pytz.timezone("America/Santiago")

SOURCE_LABELS = {
    "minvu":          "MINVU / DDU",
    "bcn":            "Biblioteca del Congreso",
    "diario-oficial": "Diario Oficial",
    "proyectos-ley":  "Proyectos de Ley",
    "contraloria":    "Contraloría General",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ult.digest")


# ─── CLIENTES ─────────────────────────────────────────────────

def get_db() -> Client:
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        raise ValueError("Faltan SUPABASE_URL o SUPABASE_SERVICE_ROLE_KEY")
    return create_client(url, key)

def get_claude():
    return anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))

def setup_resend():
    key = os.getenv("RESEND_API_KEY", "")
    if not key:
        raise ValueError("Falta RESEND_API_KEY")
    resend.api_key = key


# ─── CONSULTAS DE BASE DE DATOS ───────────────────────────────

def get_core_slugs(db: Client) -> list[str]:
    """Slugs de las fuentes marcadas como es_core=True."""
    result = db.table("sources").select("slug").eq("es_core", True).execute()
    return [r["slug"] for r in (result.data or [])]

def get_new_publications(db: Client, core_slugs: list[str]) -> list[dict]:
    """Publications nuevas (is_new=True) de las fuentes core."""
    if not core_slugs:
        return []
    result = (
        db.table("publications")
        .select("*")
        .eq("is_new", True)
        .in_("source_slug", core_slugs)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []

def get_active_users(db: Client) -> list[dict]:
    """Usuarios con email cargado en user_profiles."""
    result = (
        db.table("user_profiles")
        .select("*")
        .not_.is_("email", "null")
        .execute()
    )
    return result.data or []

def get_subscriptions(db: Client, user_id: str) -> list[dict]:
    """Subscriptions activas con notify_email=True para un usuario."""
    result = (
        db.table("subscriptions")
        .select("*")
        .eq("user_id", user_id)
        .eq("notify_email", True)
        .execute()
    )
    return result.data or []


# ─── FILTRADO ─────────────────────────────────────────────────

def filter_for_user(publications: list[dict], subs: list[dict]) -> list[dict]:
    """
    Filtra las publications según las subscriptions del usuario.
    - Sin keywords → recibe todas las de esa fuente.
    - Con keywords  → solo las que contienen alguna keyword en el título.
    """
    seen, result = set(), []
    for sub in subs:
        slug     = sub.get("source_slug", "")
        keywords = [k.lower() for k in (sub.get("keywords") or [])]
        for pub in publications:
            if pub["source_slug"] != slug or pub["id"] in seen:
                continue
            if not keywords or any(kw in pub.get("title", "").lower() for kw in keywords):
                seen.add(pub["id"])
                result.append(pub)
    return result


# ─── RESUMEN ──────────────────────────────────────────────────

def generate_summary(publications: list[dict], claude) -> str:
    """Resumen ejecutivo en viñetas generado con Claude Haiku."""
    fecha  = datetime.now(CHILE_TZ).strftime("%d de %B de %Y")
    items  = "\n".join(
        f"- [{p.get('source_slug','').upper()}] {p['title']}"
        for p in publications[:10]
    )
    prompt = (
        f"Eres un experto en urbanismo y normativa chilena. Fecha: {fecha}.\n"
        f"Resume en 5-8 viñetas concisas y prácticas para arquitectos y revisores "
        f"estas {len(publications)} novedades normativas. "
        f"Indica el impacto práctico de cada una:\n{items}"
    )
    try:
        resp = claude.messages.create(
            model=HAIKU_MODEL,
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text
    except Exception as e:
        logger.warning(f"Error generando resumen Haiku: {e}")
        return "Resumen no disponible en este envío."


# ─── EMAIL ────────────────────────────────────────────────────

def build_html(publications: list[dict], summary_md: str, fecha: str) -> str:
    """Construye el HTML del email de digest."""
    summary_html = markdown.markdown(summary_md)

    # Agrupar por fuente
    by_source: dict[str, list] = {}
    for p in publications:
        by_source.setdefault(p["source_slug"], []).append(p)

    items_html = ""
    for slug, pubs in by_source.items():
        label = SOURCE_LABELS.get(slug, slug.upper())
        items_html += f'<h3 style="color:#1a5276;margin-top:24px;font-size:15px">{label}</h3><ul style="padding-left:20px">'
        for p in pubs:
            items_html += (
                f'<li style="margin-bottom:8px">'
                f'<a href="{p.get("url","#")}" style="color:#2471a3">{p["title"]}</a>'
                f'</li>'
            )
        items_html += "</ul>"

    n    = len(publications)
    noun = f"{n} novedad{'es' if n != 1 else ''} normativa{'s' if n != 1 else ''}"

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
</head>
<body style="font-family:Arial,sans-serif;max-width:640px;margin:0 auto;padding:20px;color:#222">

  <!-- Cabecera -->
  <div style="background:#1a5276;padding:20px 24px;border-radius:8px 8px 0 0">
    <h1 style="color:#fff;margin:0;font-size:22px">ULT · Urban Lex Tracker</h1>
    <p style="color:#aed6f1;margin:6px 0 0;font-size:13px">By AGORA Revisores &nbsp;·&nbsp; {fecha}</p>
  </div>

  <!-- Cuerpo -->
  <div style="border:1px solid #d5e8f0;border-top:none;padding:24px;border-radius:0 0 8px 8px">
    <p style="font-size:16px;margin-top:0">
      Tienes <strong>{noun}</strong> desde el último digest.
    </p>

    {items_html}

    <hr style="border:none;border-top:1px solid #eee;margin:28px 0">

    <h2 style="color:#1a5276;font-size:17px">Resumen ejecutivo</h2>
    <div style="background:#f4f9fd;padding:16px 20px;border-radius:6px;line-height:1.8">
      {summary_html}
    </div>

    <hr style="border:none;border-top:1px solid #eee;margin:28px 0">

    <p style="font-size:11px;color:#aaa;margin:0">
      ULT — Urban Lex Tracker &nbsp;·&nbsp; By AGORA Revisores<br>
      Recibes este digest porque estás suscrito al seguimiento normativo urbanístico.
    </p>
  </div>
</body>
</html>"""


def send_email(to: str, html: str, n: int, fecha: str) -> bool:
    """Envía el digest vía Resend. Retorna True si fue exitoso."""
    subject = f"{SUBJECT_BASE} — {n} novedad{'es' if n != 1 else ''} · {fecha}"
    try:
        resp = resend.Emails.send({
            "from": FROM_EMAIL,
            "to":   [to],
            "subject": subject,
            "html": html,
        })
        logger.info(f"✓ Email enviado a {to} — id: {resp.get('id','?')}")
        return True
    except Exception as e:
        logger.error(f"✗ Error enviando a {to}: {e}")
        return False


# ─── REGISTRO Y LIMPIEZA ──────────────────────────────────────

def log_alerts(db: Client, user_id: str, publications: list[dict]):
    """Registra en alerts_log una fila por publicación enviada al usuario."""
    now  = datetime.now(timezone.utc).isoformat()
    rows = [
        {"user_id": user_id, "publication_id": p["id"],
         "channel": "email", "sent_at": now}
        for p in publications
    ]
    if rows:
        try:
            db.table("alerts_log").insert(rows).execute()
        except Exception as e:
            logger.warning(f"Error en alerts_log para {user_id}: {e}")

def mark_processed(db: Client, pub_ids: list[str]):
    """Marca las publications procesadas como is_new=False."""
    if not pub_ids:
        return
    try:
        db.table("publications").update({"is_new": False}).in_("id", pub_ids).execute()
        logger.info(f"Marcadas {len(pub_ids)} publications como is_new=False")
    except Exception as e:
        logger.error(f"Error marcando publications: {e}")


# ─── MAIN ─────────────────────────────────────────────────────

def main():
    logger.info("═══ ULT Digest — inicio ═══")
    fecha = datetime.now(CHILE_TZ).strftime("%d de %B de %Y")

    db    = get_db()
    claude = get_claude()
    setup_resend()

    # 1. Publicaciones nuevas de fuentes core
    core_slugs = get_core_slugs(db)
    logger.info(f"Fuentes core: {core_slugs}")

    new_pubs = get_new_publications(db, core_slugs)
    logger.info(f"Publications nuevas: {len(new_pubs)}")

    if not new_pubs:
        logger.info("Sin novedades — no se envían emails.")
        return

    # 2. Procesar cada usuario
    users      = get_active_users(db)
    sent_count = 0

    for user in users:
        email = user.get("email", "")
        if not email:
            continue

        subs = get_subscriptions(db, user["id"])
        if not subs:
            logger.info(f"{email}: sin subscriptions — omitiendo")
            continue

        user_pubs = filter_for_user(new_pubs, subs)
        if not user_pubs:
            logger.info(f"{email}: sin novedades en sus fuentes — omitiendo")
            continue

        logger.info(f"{email}: {len(user_pubs)} novedades → generando resumen...")
        summary = generate_summary(user_pubs, claude)
        html    = build_html(user_pubs, summary, fecha)

        if send_email(email, html, len(user_pubs), fecha):
            log_alerts(db, user["id"], user_pubs)
            sent_count += 1

    # 3. Marcar todas las publications core nuevas como procesadas
    # Nota: se marcan todas (enviadas o no) para que el próximo digest
    # solo procese lo realmente nuevo. En v1 se puede refinar con retry.
    all_ids = [p["id"] for p in new_pubs]
    mark_processed(db, all_ids)

    logger.info(f"═══ ULT Digest — fin · {sent_count} emails enviados ═══")


if __name__ == "__main__":
    main()
