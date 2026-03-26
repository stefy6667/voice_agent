import base64
import html
import imghdr
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.models import QRCreateResponse
from app.services.qr_store import QRStore

app = FastAPI(title="QR Studio")
store = QRStore()
app.mount("/static", StaticFiles(directory=str(Path(__file__).resolve().parent / "static")), name="static")
app.mount("/uploads", StaticFiles(directory=str(settings.storage_path)), name="uploads")


def ensure_admin(code: str) -> None:
    if code != settings.admin_access_code:
        raise HTTPException(status_code=403, detail="Cod admin invalid.")


def build_public_url(slug: str) -> str:
    return f"{settings.public_base_url.rstrip('/')}/p/{slug}"


def external_qr_url(slug: str) -> str:
    return f"https://api.qrserver.com/v1/create-qr-code/?size=800x800&data={quote(build_public_url(slug), safe='')}"


def shell(title: str, body: str, body_class: str = "") -> HTMLResponse:
    return HTMLResponse(
        f"""<!doctype html><html lang='ro'><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><link rel='stylesheet' href='/static/styles.css'></head><body class='{body_class}'>{body}</body></html>"""
    )


def render_index() -> HTMLResponse:
    cards = []
    for item in store.list_all():
        cards.append(
            f"""
            <article class='card'>
              <img src='{external_qr_url(item.slug)}' alt='QR {item.slug}'>
              <div>
                <h3>{html.escape(item.content.headline)}</h3>
                <p><strong>Slug:</strong> {item.slug}</p>
                <p><strong>Cod editare:</strong> {item.edit_code}</p>
                <p><strong>Public:</strong> <a href='/p/{item.slug}'>/p/{item.slug}</a></p>
                <p><strong>Editor:</strong> <a href='/edit/{item.slug}'>/edit/{item.slug}</a></p>
                <a class='button secondary' href='/api/qr/{item.slug}.png'>Download PNG</a>
              </div>
            </article>
            """
        )
    body = f"""
    <main class='shell'>
      <section class='hero glass'>
        <div>
          <span class='eyebrow'>Render-ready QR experience studio</span>
          <h1>Generezi QR-uri, clientul personalizează conținutul oricând.</h1>
          <p>Fluxul este exact cum ai cerut: tu creezi codul, îl descarci PNG, clientul scanează, configurează, salvează, iar la scanările următoare vede conținutul salvat. Cu butonul de editare și codul unic poate relua procesul oricând.</p>
        </div>
        <form class='admin-card' method='post' action='/api/admin/create'>
          <label>Codul tău de admin</label>
          <input type='password' name='admin_code' placeholder='ADMIN_ACCESS_CODE' required>
          <button type='submit'>Generează QR nou</button>
          <small>Setează ADMIN_ACCESS_CODE în Render înainte de producție.</small>
        </form>
      </section>
      <section class='dashboard glass'>
        <div class='section-header'>
          <h2>Codurile tale generate</h2>
          <p>Doar cine are codul tău de admin poate crea noi QR-uri. Fiecare cod are un token unic de editare pentru client.</p>
        </div>
        <div class='cards'>{''.join(cards) if cards else "<div class='empty'>Nu ai generat încă niciun QR.</div>"}</div>
      </section>
    </main>
    """
    return shell("QR Studio", body)


def render_public(record) -> HTMLResponse:
    image = f"<img class='hero-image' src='{record.content.image_path}' alt='Imagine încărcată de client'>" if record.content.image_path else ""
    video = f"<div class='video-wrap'><iframe src='{html.escape(record.content.video_url)}' title='Video personalizat' allowfullscreen></iframe></div>" if record.content.video_url else ""
    body = f"""
    <main class='public-shell' style='--accent:{record.content.accent_color}; --text-color:{record.content.text_color}; font-family:{html.escape(record.content.font_family)}; text-align:{record.content.text_align};'>
      <section class='story-card glass'>
        <span class='eyebrow'>Experiență salvată</span>
        <h1>{html.escape(record.content.headline)}</h1>
        <p>{html.escape(record.content.body_text)}</p>
        {image}
        {video}
        <a class='button' href='/edit/{record.slug}'>{html.escape(record.content.button_label)}</a>
      </section>
    </main>
    """
    return shell(record.content.headline, body, f"theme-{record.content.theme}")


def render_edit(record, unlocked: bool, code: str = "") -> HTMLResponse:
    unlock_block = f"""
      <form method='post' action='/unlock/{record.slug}' class='unlock-form'>
        <label>Cod alfanumeric de editare</label>
        <input type='text' name='code' placeholder='ex: {record.edit_code}' required>
        <button type='submit'>Deblochează editorul</button>
      </form>
    """ if not unlocked else f"""
      <form class='editor-form' method='post' action='/api/qr/{record.slug}/content' enctype='multipart/form-data'>
        <input type='hidden' name='edit_code' value='{html.escape(code)}'>
        <label>Titlu</label><input type='text' name='headline' value='{html.escape(record.content.headline)}' required>
        <label>Text</label><textarea name='body_text' rows='5' required>{html.escape(record.content.body_text)}</textarea>
        <label>Text buton</label><input type='text' name='button_label' value='{html.escape(record.content.button_label)}' required>
        <div class='grid-two'>
          <div><label>Temă</label><select name='theme'>{''.join([f"<option value='{t}' {'selected' if record.content.theme==t else ''}>{t}</option>" for t in ['aurora','midnight','sunset']])}</select></div>
          <div><label>Font</label><select name='font_family'>{''.join([f"<option value='{f}' {'selected' if record.content.font_family==f else ''}>{f}</option>" for f in ['Inter','Georgia','Verdana']])}</select></div>
        </div>
        <div class='grid-two'>
          <div><label>Aliniere text</label><select name='text_align'>{''.join([f"<option value='{a}' {'selected' if record.content.text_align==a else ''}>{a}</option>" for a in ['left','center']])}</select></div>
          <div><label>Link video embed</label><input type='url' name='video_url' value='{html.escape(record.content.video_url or '')}'></div>
        </div>
        <div class='grid-two'>
          <div><label>Culoare accent</label><input type='color' name='accent_color' value='{record.content.accent_color}'></div>
          <div><label>Culoare text</label><input type='color' name='text_color' value='{record.content.text_color}'></div>
        </div>
        <label>Poza clientului</label><input type='file' name='image' accept='image/*'>
        <button type='submit'>Salvează experiența</button>
      </form>
    """
    preview_img = f"<img class='hero-image' src='{record.content.image_path}' alt='preview'>" if record.content.image_path else ""
    body = f"""
    <main class='editor-layout'>
      <section class='glass editor-panel'>
        <h1>Personalizează codul QR</h1>
        <p>Clientul introduce codul alfanumeric primit, apoi poate modifica textul, culorile, fontul, poza și video-ul de câte ori dorește.</p>
        {unlock_block}
      </section>
      <section class='glass preview-panel'>
        <span class='eyebrow'>Preview</span>
        <h2>{html.escape(record.content.headline)}</h2>
        <p>{html.escape(record.content.body_text)}</p>
        {preview_img}
        <a class='button' href='/p/{record.slug}'>Vezi pagina publică</a>
      </section>
    </main>
    """
    return shell(f"Editează {record.slug}", body, f"theme-{record.content.theme}")


def file_to_data_url(raw: bytes, content_type: str | None) -> str:
    mime = content_type or "application/octet-stream"
    return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"


@app.get("/", response_class=HTMLResponse)
async def home() -> HTMLResponse:
    return render_index()


@app.get("/health")
async def health() -> dict:
    return {"ok": True, "app": settings.app_name, "items": len(store.list_all())}


@app.post("/api/admin/create", response_model=QRCreateResponse)
async def create_qr(admin_code: str = Form(...)) -> QRCreateResponse:
    ensure_admin(admin_code)
    record = store.create()
    return QRCreateResponse(qr_id=record.qr_id, edit_code=record.edit_code, slug=record.slug, qr_png_url=f"/api/qr/{record.slug}.png", public_url=build_public_url(record.slug))


@app.get("/api/qr/{slug}.png")
async def qr_png(slug: str) -> RedirectResponse:
    if store.get_by_slug(slug) is None:
        raise HTTPException(status_code=404, detail="QR inexistent")
    return RedirectResponse(url=external_qr_url(slug), status_code=307)


@app.get("/p/{slug}", response_class=HTMLResponse)
async def public_page(slug: str) -> HTMLResponse:
    record = store.get_by_slug(slug)
    if record is None:
        raise HTTPException(status_code=404, detail="Pagina nu există.")
    return render_public(record)


@app.get("/edit/{slug}", response_class=HTMLResponse)
async def edit_page(slug: str, code: str | None = None) -> HTMLResponse:
    record = store.get_by_slug(slug)
    if record is None:
        raise HTTPException(status_code=404, detail="Cod inexistent.")
    return render_edit(record, code == record.edit_code if code else False, code or "")


@app.post("/api/qr/{slug}/content")
async def update_qr_content(
    slug: str,
    edit_code: str = Form(...),
    headline: str = Form(...),
    body_text: str = Form(...),
    button_label: str = Form(...),
    theme: str = Form(...),
    font_family: str = Form(...),
    text_align: str = Form(...),
    accent_color: str = Form(...),
    text_color: str = Form(...),
    video_url: str = Form(""),
    image: UploadFile | None = File(default=None),
) -> JSONResponse:
    payload = {
        "headline": headline,
        "body_text": body_text,
        "button_label": button_label,
        "theme": theme,
        "font_family": font_family,
        "text_align": text_align,
        "accent_color": accent_color,
        "text_color": text_color,
        "video_url": video_url or None,
    }
    if image is not None and image.filename:
        raw = await image.read()
        if len(raw) > settings.max_upload_size_mb * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Fișierul este prea mare.")
        if imghdr.what(None, raw) not in {"png", "jpeg", "gif", "webp"}:
            raise HTTPException(status_code=400, detail="Imagine invalidă.")
        payload["image_path"] = file_to_data_url(raw, image.content_type)
    record = store.update(slug, edit_code, payload)
    if record is None:
        raise HTTPException(status_code=403, detail="Codul de editare este invalid.")
    return JSONResponse({"ok": True, "slug": slug, "updated_at": record.updated_at})


@app.post("/unlock/{slug}")
async def unlock(slug: str, code: str = Form(...)) -> RedirectResponse:
    record = store.get_by_slug(slug)
    if record is None:
        raise HTTPException(status_code=404, detail="Cod inexistent.")
    if code != record.edit_code:
        raise HTTPException(status_code=403, detail="Cod de editare invalid.")
    return RedirectResponse(url=f"/edit/{slug}?code={code}", status_code=303)
