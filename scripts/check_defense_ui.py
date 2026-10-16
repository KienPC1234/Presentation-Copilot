"""Optional local browser check: requires Playwright and Microsoft Edge."""
import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading

from playwright.async_api import async_playwright, expect

ROOT = Path(__file__).resolve().parents[1]


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        data = (ROOT / "server/web/index.html").read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


async def check():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    fixture = {"questions": [{"question": f"Câu {i}: <img src=x onerror=alert(1)>", "purpose": "Kiểm tra bằng chứng",
        "answer_outline": ["Đối chiếu tài liệu"], "follow_up": "Căn cứ đâu?", "evidence_status": "cited", "evidence_ids": ["e1"]}
        for i in range(6)], "evidence": [{"id": "e1", "excerpt": "Nội dung <script>không được thực thi</script>"}]}
    mode = ["success"]
    errors = []
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(channel="msedge", headless=True)
            page = await browser.new_page(viewport={"width": 390, "height": 900})
            page.on("pageerror", lambda error: errors.append(str(error)))

            async def api(route):
                if route.request.url.endswith("/api/defense/prepare"):
                    await asyncio.sleep(0.4)
                    await route.fulfill(status=200 if mode[0] == "success" else 503,
                        content_type="application/json", body=json.dumps(fixture if mode[0] == "success" else {"detail": "Model unavailable"}))
                else:
                    await route.fulfill(content_type="application/json", body='{"whisper":{},"total_chunks":0}')

            await page.route("**/api/**", api)
            await page.goto(f"http://127.0.0.1:{server.server_port}", wait_until="networkidle")
            await page.get_by_role("button", name="CHUẨN BỊ PHẢN BIỆN", exact=True).click()
            await page.get_by_label("Tên sản phẩm / đề tài").fill("Sản phẩm kiểm thử")
            button = page.get_by_role("button", name="Tạo bộ câu hỏi", exact=True)
            await button.click()
            await expect(button).to_be_disabled()
            await expect(page.locator("#defenseStatus")).to_contain_text("Đã chuẩn bị 6")
            await expect(page.locator("#defenseQuestions article")).to_have_count(6)
            await expect(page.locator("#defenseQuestions img")).to_have_count(0)
            async with page.expect_download() as pending:
                await page.get_by_role("button", name="Lưu bộ câu hỏi", exact=True).click()
            download = await pending.value
            assert download.suggested_filename == "defense-preparation.json"
            target = ROOT / "validation/ui-private"
            target.mkdir(parents=True, exist_ok=True)
            await download.save_as(target / "defense-preparation.json")
            assert len(json.loads((target / "defense-preparation.json").read_text(encoding="utf-8"))["questions"]) == 6
            for width in (320, 390, 1440):
                await page.set_viewport_size({"width": width, "height": 900})
                if not await page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"):
                    print(await page.evaluate("Array.from(document.querySelectorAll('body *')).filter(e => e.getBoundingClientRect().right > innerWidth + 1).slice(0,8).map(e => [e.tagName, e.id, e.className, Math.round(e.getBoundingClientRect().right)])"))
                    raise AssertionError(f"Horizontal overflow at {width}px")
            await page.set_viewport_size({"width": 390, "height": 900})
            await page.screenshot(path=str(target / "defense-390.png"), full_page=True)
            mode[0] = "error"
            await button.click()
            await expect(page.locator("#defenseStatus")).to_contain_text("Không hoàn tất")
            await expect(page.locator("#defenseDownload")).to_be_disabled()
            await expect(page.locator("#defenseQuestions article")).to_have_count(0)
            assert not errors, errors
            await browser.close()
            print("PASS: loading, success, JSON export, error, escaped model text, 320/390/1440px")
    finally:
        server.shutdown()


if __name__ == "__main__":
    asyncio.run(check())
