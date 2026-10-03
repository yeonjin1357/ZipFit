from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .catalog import ROOT, load_catalog, schedule
from .models import MatchRequest, Profile
from .middleware import ProfileBodyLimit
from .rules import KST, evaluate
from .settings import Settings


def create_app(settings=None):
    settings = settings or Settings.from_env()
    app = FastAPI(title="ZipFit", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(ProfileBodyLimit)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts), www_redirect=False)
    app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")

    @app.middleware("http")
    async def headers(request, call_next):
        from fastapi.responses import JSONResponse
        origin = request.headers.get("origin")
        scheme = "https" if settings.production else request.url.scheme
        expected_origin = scheme + "://" + request.headers.get("host", "")
        if request.method == "POST" and origin and origin != expected_origin:
            response = JSONResponse({"detail":"이 사이트에서만 요청할 수 있어요."}, status_code=403)
        else:
            response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if settings.production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    app.add_api_route("/", index, methods=["GET"])
    app.add_api_route("/api/notices", notices, methods=["GET"])
    app.add_api_route("/api/match", match, methods=["POST"])
    app.add_api_route("/api/health", health, methods=["GET"])
    app.add_api_route("/api/documents/{notice_id:path}", document, methods=["GET"])
    app.add_api_route("/api/calendar/{notice_id:path}", calendar, methods=["GET"])
    app.add_api_route("/api/housing-document/{notice_id:path}", housing_document, methods=["GET"])
    return app


def index():
    return FileResponse(ROOT / "static/index.html")


def results(profile):
    catalog = load_catalog()
    now = datetime.now(KST)
    notices = [{**n,"schedule":schedule(n, now),"evaluation":evaluate(n,profile,now)} for n in catalog["notices"]]
    return {"as_of":now.isoformat(),"sources":catalog["sources"],"notices":notices,
            "discovery":catalog.get("discovery"), "schedule_refresh":catalog.get("schedule_refresh"),
            "coverage":{"source_posts":len(notices),"recruitment_candidates":sum(n["kind"]=="recruitment" for n in notices),"reviewed_notices":sum(bool(n.get("rule_model")) for n in notices),"reviewed_tracks":sum(len(n["evaluation"]["tracks"]) for n in notices)}}


def notices():
    return results(Profile())


def match(request: MatchRequest):
    # Profile data is neither persisted nor sent to an external service.
    return results(request.profile)


def health():
    return {"ok":True,"version":"0.1.0"}


def document(notice_id: str):
    catalog = load_catalog()
    notice = next((n for n in catalog["notices"] if n["id"] == notice_id), None)
    if not notice or not notice.get("document"):
        raise HTTPException(404, "저장한 공고문이 없어요.")
    path = (ROOT / notice["document"]["path"]).resolve()
    if not path.is_relative_to(ROOT / "research") or path.suffix != ".pdf" or not path.is_file():
        raise HTTPException(404, "공고문을 찾지 못했어요.")
    return FileResponse(path, media_type="application/pdf")


def calendar(notice_id: str):
    from fastapi.responses import Response
    from .calendar import export_calendar
    n=next((n for n in load_catalog()['notices'] if n['id']==notice_id),None)
    if not n: raise HTTPException(404,'공고를 찾지 못했어요.')
    try: content=export_calendar(n)
    except ValueError as exc: raise HTTPException(409,str(exc))
    return Response(content,media_type='text/calendar',headers={'Content-Disposition':'attachment; filename="zipfit-application.ics"'})


def housing_document(notice_id: str):
    n=next((n for n in load_catalog()['notices'] if n['id']==notice_id),None)
    if not n or not n.get('housing_document'): raise HTTPException(404,'공급목록을 찾지 못했어요.')
    path=(ROOT/n['housing_document']['path']).resolve()
    if not path.is_relative_to(ROOT/'research') or path.suffix!='.xlsx' or not path.is_file(): raise HTTPException(404,'공급목록을 찾지 못했어요.')
    return FileResponse(path,filename='housing-list.xlsx',media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


app = create_app()
