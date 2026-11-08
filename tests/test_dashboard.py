import threading
import urllib.request

from freefox.config import CollectorConfig
from freefox.dashboard import HTML, DashboardServer, _load_dashboard_html


def test_dashboard_html_content():
    html = _load_dashboard_html()
    assert "<!doctype html>" in html
    assert "<title>FreeFox - Tableau de bord</title>" in html
    assert html == HTML


def test_dashboard_server_get_index(tmp_path):
    cfg_file = tmp_path / "cfg.yaml"
    queue_db = tmp_path / "queue.db"
    watch_dir = tmp_path / "watch"
    watch_dir.mkdir()

    cfg_file.write_text(
        f"robot_id: test-bot\n"
        f"watch:\n  directory: {watch_dir}\n"
        f"queue_db: {queue_db}\n"
    )
    cfg = CollectorConfig.from_yaml(cfg_file)
    server = DashboardServer(("127.0.0.1", 0), cfg)
    port = server.server_address[1]

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        url = f"http://127.0.0.1:{port}/"
        with urllib.request.urlopen(url) as resp:
            assert resp.status == 200
            assert "text/html" in resp.headers.get("Content-Type", "")
            body = resp.read().decode("utf-8")
            assert "<title>FreeFox - Tableau de bord</title>" in body

        # Check logo endpoint
        logo_url = f"http://127.0.0.1:{port}/brand/freefox.png"
        with urllib.request.urlopen(logo_url) as resp:
            assert resp.status == 200
            assert "image/png" in resp.headers.get("Content-Type", "")
            assert len(resp.read()) > 0
    finally:
        server.shutdown()
        server.server_close()
        if hasattr(server.queue, "conn") and server.queue.conn:
            server.queue.conn.close()
