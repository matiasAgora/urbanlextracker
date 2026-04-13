# Force reload - Updated with expert UX/UI routes
import os
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse, Response

# weasyprint requiere librerías GTK nativas no disponibles en Windows sin instalación adicional
# from weasyprint import HTML
import io
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

import database
import auth
import scrapers

load_dotenv()

app = FastAPI(title="Urban Lex Tracker", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Montar carpeta estática
app.mount("/static", StaticFiles(directory="static"), name="static")

# ─── Startup ───


@app.on_event("startup")
def on_startup():
    database.init_db()
    auth.seed_demo_user()
    print("[ULT] Base de datos inicializada.")
    print("[ULT] Urban Lex Tracker v2.0 — listo en http://127.0.0.1:8000")


# ─── Pydantic Models ───


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    password: str
    nombre: str = ""
    profesion: str = ""


class KeywordRequest(BaseModel):
    keyword: str


# ════════════════════════════════════════════════
# AUTH ENDPOINTS
# ════════════════════════════════════════════════


@app.post("/api/auth/login")
def api_login(data: LoginRequest):
    return auth.login_user(data.email, data.password)


@app.post("/api/auth/register")
def api_register(data: RegisterRequest):
    return auth.register_user(data.email, data.password, data.nombre, data.profesion)


@app.get("/api/auth/me")
def api_me(request: Request):
    user = auth.require_auth(request)
    keywords = database.get_user_keywords(user["id"])
    return {
        "id": user["id"],
        "email": user["email"],
        "nombre": user["nombre"],
        "profesion": user["profesion"],
        "keywords": keywords,
    }


# ════════════════════════════════════════════════
# SCRAPER ENDPOINTS
# ════════════════════════════════════════════════


@app.get("/api/scrape/minvu")
def api_scrape_minvu(request: Request):
    auth.require_auth(request)
    result = scrapers.scrape_minvu()
    return {
        "status": "success",
        "date": scrapers.hoy_chile(),
        "html_report": result["report_html"],
        "raw_markdown": result.get("report_md", ""),
        "items_count": result["count"],
    }


@app.get("/api/scrape/diario-oficial")
def api_scrape_diario_oficial(request: Request):
    auth.require_auth(request)
    result = scrapers.scrape_diario_oficial()
    return {
        "status": "success",
        "date": scrapers.hoy_chile(),
        "html_report": result["report_html"],
        "raw_markdown": result.get("report_md", ""),
        "items_count": result["count"],
    }


@app.get("/api/scrape/contraloria")
def api_scrape_contraloria(request: Request):
    auth.require_auth(request)
    result = scrapers.scrape_contraloria()
    return {
        "status": "success",
        "date": scrapers.hoy_chile(),
        "html_report": result["report_html"],
        "raw_markdown": result.get("report_md", ""),
        "items_count": result["count"],
    }


@app.get("/api/scrape/bcn")
def api_scrape_bcn(request: Request):
    auth.require_auth(request)
    result = scrapers.scrape_bcn()
    return {
        "status": "success",
        "date": scrapers.hoy_chile(),
        "html_report": result["report_html"],
        "raw_markdown": result.get("report_md", ""),
        "items_count": result["count"],
    }


@app.get("/api/scrape/poder-judicial")
def api_scrape_pj(request: Request):
    auth.require_auth(request)
    result = scrapers.scrape_poder_judicial()
    return {
        "status": "success",
        "date": scrapers.hoy_chile(),
        "html_report": result["report_html"],
        "raw_markdown": result.get("report_md", ""),
        "items_count": result["count"],
    }


@app.get("/api/scrape/prensa")
def api_scrape_prensa(request: Request):
    auth.require_auth(request)
    result = scrapers.scrape_prensa()
    return {
        "status": "success",
        "date": scrapers.hoy_chile(),
        "html_report": result["report_html"],
        "raw_markdown": result.get("report_md", ""),
        "items_count": result["count"],
    }


@app.get("/api/scrape/proyectos-ley")
def api_scrape_proyectos(request: Request):
    auth.require_auth(request)
    result = scrapers.scrape_proyectos_ley()
    return {
        "status": "success",
        "date": scrapers.hoy_chile(),
        "html_report": result["report_html"],
        "raw_markdown": result.get("report_md", ""),
        "items_count": result["count"],
    }


@app.get("/api/scrape/ipt")
def api_scrape_ipt(request: Request):
    auth.require_auth(request)
    result = scrapers.scrape_ipt()
    return {
        "status": "success",
        "date": scrapers.hoy_chile(),
        "html_report": result["report_html"],
        "raw_markdown": result.get("report_md", ""),
        "items_count": result["count"],
    }


@app.get("/api/scrape/all")
def api_scrape_all(request: Request):
    auth.require_auth(request)
    result = scrapers.run_all_scrapers()
    return result


class SelectedSourcesRequest(BaseModel):
    sources: list[str]


@app.post("/api/scrapers/run-selected")
def api_scrape_selected(request: Request, data: SelectedSourcesRequest):
    auth.require_auth(request)
    results = {}
    total = 0
    for name in data.sources:
        if name in scrapers.SCRAPERS:
            try:
                res = scrapers.SCRAPERS[name]()
                results[name] = res
                total += res.get("count", 0)
            except Exception as e:
                database.save_scrape_history(name, 0, "error", str(e))
    return {
        "status": "success",
        "total_items": total,
        "sources": results,
        "date": scrapers.hoy_chile(),
    }


@app.get("/api/dashboard/summary")
def api_dashboard_summary(request: Request):
    auth.require_auth(request)
    sources_status = database.get_sources_status()

    # Define the 8 main sources by their IDs to avoid encoding issues
    main_source_ids = [
        "diario-oficial",
        "contraloria",
        "minvu",
        "bcn",
        "poder-judicial",
        "prensa",
        "proyectos-ley",
        "ipt",
    ]

    results = []
    for source_id in main_source_ids:
        # Find status from DB
        status_entry = next(
            (s for s in sources_status if s["source"] == source_id), None
        )

        # Get last finding
        last_alert = database.get_alerts(source=source_id, limit=1)
        last_finding = (
            last_alert[0]["title"] if last_alert else "Sin hallazgos recientes."
        )

        display_name = (
            status_entry["display_name"]
            if status_entry
            else source_id.replace("-", " ").title()
        )

        results.append(
            {
                "name": display_name,
                "source_id": source_id,
                "status": status_entry["status"] if status_entry else "Offline",
                "last_sync": status_entry["last_scrape"] if status_entry else "---",
                "items_found_today": status_entry["items_found"] if status_entry else 0,
                "last_finding": last_finding,
            }
        )

    return {"bot_board": results}


@app.get("/api/history/{source}")
def api_history_source(request: Request, source: str):
    auth.require_auth(request)

    # Get bot status for metadata
    status = database.get_sources_status()
    bot_status = next(
        (s for s in status if s["source"] == source or s["display_name"] == source),
        None,
    )

    actual_source = bot_status["source"] if bot_status else source

    # Get all alerts for this source, limit 100 for now
    history = database.get_alerts(source=actual_source, limit=100)

    return {
        "source": bot_status["display_name"] if bot_status else source,
        "source_id": actual_source,
        "metadata": bot_status,
        "history": history,
    }

    # 1. Gather today's alerts for the selected sources
    combined_texts = []
    for source in data.sources:
        # get today's alerts from database for this source
        alerts = database.get_alerts(source=source, limit=10, today_only=True)
        disp_name = source_names.get(source, source)
        if alerts:
            combined_texts.append(
                f"### Fuente: {disp_name}\n"
                + "\n".join([f"- {a['title']} (URL: {a['url']})" for a in alerts])
            )
        else:
            combined_texts.append(
                f"### Fuente: {disp_name}\n- Sin hallazgos normativos el día de hoy."
            )

    texto_base = "\n\n".join(combined_texts)

    # 2. Call Gemini
    prompt = f"""Eres un analista legal experto en Chile. Redacta un INFORME EJECUTIVO CONSOLIDADO (estilo oficina formal) 
    con los hallazgos normativos de hoy: {scrapers.hoy_chile()}.
    Si una fuente no tiene hallazgos, indícalo formalmente ("Sin novedades o modificaciones registradas el día de hoy").
    Usa formato Markdown profesional.
    
    Datos recopilados hoy por el sistema:
    {texto_base}
    """

    informe_md = scrapers.call_gemini(prompt)
    import markdown

    return {
        "status": "success",
        "date": scrapers.hoy_chile(),
        "html_report": markdown.markdown(informe_md),
        "raw_markdown": informe_md,
    }


# ════════════════════════════════════════════════
# DATA ENDPOINTS
# ════════════════════════════════════════════════


@app.get("/api/alerts")
def api_get_alerts(
    request: Request,
    source: str = None,
    limit: int = 50,
    offset: int = 0,
    search: str = None,
):
    auth.require_auth(request)
    alerts = database.get_alerts(
        source=source, limit=limit, offset=offset, search=search
    )
    counts = database.get_alert_count()
    return {"alerts": alerts, "meta": counts}


@app.get("/api/sources/status")
def api_sources_status(request: Request):
    auth.require_auth(request)
    return database.get_sources_status()


@app.get("/api/stats")
def api_stats(request: Request):
    auth.require_auth(request)
    counts = database.get_alert_count()
    sources = database.get_sources_status()
    active = sum(1 for s in sources if s["status"] == "success")
    return {
        "processed_today": counts["today"],
        "new_findings": counts["new"],
        "total_alerts": counts["total"],
        "active_sources": active,
        "total_sources": len(sources),
        "uptime": "99.9%",
    }


@app.post("/api/alerts/mark-read")
def api_mark_read(request: Request):
    auth.require_auth(request)
    database.mark_alerts_read()
    return {"status": "ok"}


# Keywords
@app.get("/api/keywords")
def api_get_keywords(request: Request):
    user = auth.require_auth(request)
    return {"keywords": database.get_user_keywords(user["id"])}


@app.post("/api/keywords")
def api_add_keyword(request: Request, data: KeywordRequest):
    user = auth.require_auth(request)
    ok = database.add_user_keyword(user["id"], data.keyword)
    return {"status": "added" if ok else "already_exists"}


@app.delete("/api/keywords/{keyword}")
def api_remove_keyword(keyword: str, request: Request):
    user = auth.require_auth(request)
    database.remove_user_keyword(user["id"], keyword)
    return {"status": "removed"}


# Profile update
class ProfileRequest(BaseModel):
    nombre: str = None
    profesion: str = None


@app.put("/api/auth/profile")
def api_update_profile(request: Request, data: ProfileRequest):
    user = auth.require_auth(request)
    database.update_user(user["id"], data.nombre, data.profesion)
    return {"status": "updated"}


# ════════════════════════════════════════════════

# PDF Report Generation
# ... (código anterior)


@app.get("/api/report/generate")
def generate_pdf_report(request: Request):
    auth.require_auth(request)
    # WeasyPrint desactivado temporalmente — requiere GTK nativo en Windows
    # Para habilitar: instalar GTK3 runtime desde https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer
    raise HTTPException(
        status_code=503,
        detail="Generación de PDF temporalmente desactivada. WeasyPrint requiere GTK3 runtime en Windows.",
    )


# ... (resto del código)

# ════════════════════════════════════════════════

PROTECTED_PAGES = {
    "dashboard",
    "alertas",
    "configuracion",
    "detalle",
    "lectura",
    "onboarding_fuentes",
    "onboarding_plan",
    "onboarding_exito",
}
PUBLIC_PAGES = {"index", "login", "registro", "pricing_1", "pricing_2", "landing"}


def get_html(filename: str) -> str:
    file_path = os.path.join("static", "html", filename)
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    return f"<h1>404 — Página no encontrada ({filename})</h1>"


@app.get("/", response_class=HTMLResponse)
def index():
    return get_html("index.html")


@app.get("/login", response_class=HTMLResponse)
def login():
    return get_html("login.html")


@app.get("/registro", response_class=HTMLResponse)
def registro():
    return get_html("registro.html")


@app.get("/pricing", response_class=HTMLResponse)
def pricing():
    return get_html("pricing.html")


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    return get_html("dashboard.html")


@app.get("/alertas", response_class=HTMLResponse)
def alertas():
    return get_html("alertas.html")


@app.get("/configuracion", response_class=HTMLResponse)
def configuracion():
    return get_html("configuracion.html")


@app.get("/detalle", response_class=HTMLResponse)
def detalle():
    return get_html("detalle.html")


@app.get("/lectura", response_class=HTMLResponse)
def lectura():
    return get_html("lectura.html")


@app.get("/{page}", response_class=HTMLResponse)
def catch_all(page: str):
    return get_html(f"{page}.html" if not page.endswith(".html") else page)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
