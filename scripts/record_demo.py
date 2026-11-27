"""Start the app, ask real questions in a headless browser, and save screenshots and an animated GIF to docs/."""
import io
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
DOCS, PORT = ROOT / "docs", 8597
QUESTIONS = [("region", "What was net revenue by region last quarter?"), ("monthly", "Show monthly net revenue in 2026"),
             ("margin", "Which 5 brands had the highest gross margin percentage this year?"), ("blocked", "Delete all orders from 2025")]


def wait_for(url: str, seconds: int = 60) -> None:
    for _ in range(seconds):
        try:
            urllib.request.urlopen(url, timeout=2)
            return
        except OSError:
            time.sleep(1)
    raise RuntimeError("the app did not start")


def main() -> None:
    DOCS.mkdir(exist_ok=True)
    server = subprocess.Popen([sys.executable, "-m", "streamlit", "run", str(ROOT / "analyst" / "app.py"), "--server.headless", "true",
                               "--server.port", str(PORT), "--browser.gatherUsageStats", "false", "--client.toolbarMode", "minimal"],
                              cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    frames = []
    try:
        wait_for(f"http://localhost:{PORT}/_stcore/health")
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 960}, color_scheme="light")
            for name, question in QUESTIONS:
                page.goto(f"http://localhost:{PORT}", wait_until="networkidle")
                box = page.get_by_label("Question")
                box.wait_for()
                frames.append((page.screenshot(), 700))
                box.fill(question)
                frames.append((page.screenshot(), 900))
                box.press("Enter")
                page.get_by_text("attempt(s)").wait_for(timeout=90_000)
                time.sleep(2.5)                       # let the chart finish drawing
                shot = page.screenshot()
                (DOCS / f"{name}.png").write_bytes(shot)
                frames.append((shot, 3500))
                print("captured", name)
            browser.close()
    finally:
        server.terminate()
    images = [Image.open(io.BytesIO(b)).convert("RGB").resize((960, 720), Image.LANCZOS) for b, _ in frames]
    paletted = [i.quantize(colors=128, method=Image.MEDIANCUT) for i in images]
    paletted[0].save(DOCS / "demo.gif", save_all=True, append_images=paletted[1:], duration=[d for _, d in frames], loop=0, optimize=True)
    print("docs/demo.gif", (DOCS / "demo.gif").stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main()
