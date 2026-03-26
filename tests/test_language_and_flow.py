from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_check():
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json()['ok'] is True


def test_admin_creates_qr_and_updates_content():
    create = client.post('/api/admin/create', data={'admin_code': 'admin-qr-2026'})
    assert create.status_code == 200
    payload = create.json()
    public_page = client.get(f"/p/{payload['slug']}")
    assert public_page.status_code == 200

    edit_page = client.get(f"/edit/{payload['slug']}?code={payload['edit_code']}")
    assert edit_page.status_code == 200

    update = client.post(
        f"/api/qr/{payload['slug']}/content",
        data={
            'edit_code': payload['edit_code'],
            'headline': 'Invitație personalizată',
            'body_text': 'Mesaj nou pentru client.',
            'button_label': 'Editează din nou',
            'theme': 'sunset',
            'font_family': 'Verdana',
            'text_align': 'center',
            'accent_color': '#000000',
            'text_color': '#ffffff',
            'video_url': 'https://www.youtube.com/embed/dQw4w9WgXcQ',
        },
    )
    assert update.status_code == 200
    public_page_after = client.get(f"/p/{payload['slug']}")
    assert 'Invitație personalizată' in public_page_after.text
    assert 'Mesaj nou pentru client.' in public_page_after.text
