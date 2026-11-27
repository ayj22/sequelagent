"""Start the app, type real questions in a headless browser, and save screenshots and an animated GIF to docs/."""
import io
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
DOCS, PORT = ROOT / "docs", 8597
SIZE = (1280, 940)
OUT_WIDTH = 960
QUESTIONS = [("region", "What was net revenue by region last quarter?", "A business question in plain English"),
             ("monthly", "Show monthly net revenue in 2026", "Trends become line charts"),
             ("margin", "Which 5 brands had the highest gross margin percentage this year?", "Metrics follow one shared definition"),
             ("blocked", "Delete all orders from 2025", "Unsafe requests are refused")]


def wait_for(url: str, seconds: int = 60) -> None:
    for _ in range(seconds):
        try:
            urllib.request.urlopen(url, timeout=2)
            return
        except OSError:
            time.sleep(1)
    raise RuntimeError("the app did not start")


def captioned(png: bytes, caption: str) -> Image.Image:
    """The screenshot scaled down, with a caption bar that says what the viewer is looking at."""
    shot = Image.open(io.BytesIO(png)).convert("RGB")
    height = round(shot.height * OUT_WIDTH / shot.width)
    frame = Image.new("RGB", (OUT_WIDTH, height + 48), (20, 22, 43))
    frame.paste(shot.resize((OUT_WIDTH, height), Image.LANCZOS), (0, 0))
    draw = ImageDraw.Draw(frame)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 22)
    except OSError:
        font = ImageFont.load_default(22)
    width = draw.textlength(caption, font=font)
    draw.text(((OUT_WIDTH - width) / 2, height + 11), caption, font=font, fill=(255, 255, 255))
    return frame


def main() -> None:
    DOCS.mkdir(exist_ok=True)
    server = subprocess.Popen([sys.executable, "-m", "streamlit", "run", str(ROOT / "analyst" / "app.py"), "--server.headless", "true",
                               "--server.port", str(PORT)], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    frames: list[tuple[Image.Image, int]] = []      # (picture, milliseconds on screen)
    try:
        wait_for(f"http://localhost:{PORT}/_stcore/health")
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page(viewport={"width": SIZE[0], "height": SIZE[1]}, color_scheme="light")
            page.goto(f"http://localhost:{PORT}", wait_until="networkidle")
            box = page.get_by_label("Your question")
            box.wait_for()
            time.sleep(1.5)

            def snap(caption: str, ms: int) -> bytes:
                png = page.screenshot(caret="initial")
                frames.append((captioned(png, caption), ms))
                return png

            (DOCS / "home.png").write_bytes(snap("Meet QuerySherpa: ask your data in plain English", 3500))
            for number, (name, question, caption) in enumerate(QUESTIONS, 1):
                title = f"{number} of {len(QUESTIONS)} · {caption}"
                if number > 1:                                   # each question starts from a clean screen
                    page.goto(f"http://localhost:{PORT}", wait_until="networkidle")
                    box.wait_for()
                    time.sleep(1.2)
                box.click()
                snap(title, 1100)
                for i, char in enumerate(question, 1):          # type it out, a few letters per frame
                    box.press_sequentially(char)
                    if i % 3 == 0 or i == len(question):
                        snap(title, 140)
                snap(title, 1400)
                page.get_by_role("button", name="Ask →").click()
                started = time.monotonic()
                done = page.locator(".card .text")
                page.wait_for_timeout(250)
                while time.monotonic() - started < 90:
                    if page.locator("[data-testid=stStatusWidget]").count() == 0 and done.count() and \
                            page.get_by_text("attempt(s)").count():
                        break
                    snap(title + " · working…", 450)
                    page.wait_for_timeout(350)
                try:
                    page.get_by_text("attempt(s)").wait_for(timeout=45_000)
                except Exception:
                    (DOCS / "failure.png").write_bytes(page.screenshot(full_page=True))
                    print("typed:", box.input_value(), flush=True)
                    raise
                time.sleep(2.5)                                  # let the chart finish drawing
                page.locator(".card").first.evaluate("e => e.scrollIntoView({block: 'start', behavior: 'instant'})")
                page.evaluate("() => document.querySelector('[data-testid=stMain]').scrollBy(0, -70)")
                time.sleep(0.8)
                (DOCS / f"{name}.png").write_bytes(snap(title, 5500))
                if name == "region":
                    page.get_by_text("See the SQL").click()
                    time.sleep(0.8)
                    page.get_by_text("See the SQL").evaluate("e => e.scrollIntoView({block: 'center', behavior: 'instant'})")
                    time.sleep(0.5)
                    (DOCS / "sql.png").write_bytes(snap("Every answer shows the SQL behind it", 4500))
                print("captured", name)
            browser.close()
    finally:
        server.terminate()
    images = [image.quantize(colors=160, method=Image.MEDIANCUT, dither=Image.Dither.NONE) for image, _ in frames]
    durations = [ms for _, ms in frames]
    images[0].save(DOCS / "demo.gif", save_all=True, append_images=images[1:], duration=durations, loop=0, optimize=True)
    print(f"docs/demo.gif {(DOCS / 'demo.gif').stat().st_size // 1024} KB, {len(images)} frames, {sum(durations) / 1000:.0f} s")


if __name__ == "__main__":
    main()
