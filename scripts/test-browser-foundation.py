"""Phase 6 browser foundation policy and extraction checks."""

from __future__ import annotations

import asyncio
import os


async def main() -> None:
    os.environ["BROWSER_ENABLED"] = "true"
    os.environ["BROWSER_HEADLESS"] = "true"
    os.environ["BROWSER_ALLOWED_DOMAINS"] = "example.com"
    os.environ["BROWSER_ALLOWED_SCHEMES"] = "https"
    os.environ["BROWSER_MAX_SESSIONS"] = "2"
    os.environ["BROWSER_MAX_TEXT_CHARS"] = "5000"

    from app.services.browser import BrowserPolicyError, browser_manager, validate_url

    assert validate_url("https://example.com").hostname == "example.com"
    for blocked_url in (
        "http://example.com",
        "file:///C:/Windows/win.ini",
        "javascript:alert(1)",
        "https://evil-example.com",
        "https://127.0.0.1",
    ):
        try:
            validate_url(blocked_url)
        except BrowserPolicyError:
            pass
        else:
            raise AssertionError(f"policy accepted blocked URL: {blocked_url}")

    session = await browser_manager.create_and_navigate("https://example.com")
    assert session.state == "active"
    extracted = await browser_manager.scrape(session.session_id)
    assert extracted["title"]
    assert "Example Domain" in extracted["text"]
    assert extracted["session_id"] == session.session_id

    info = await browser_manager.get(session.session_id)
    assert info.current_url.startswith("https://example.com")
    assert await browser_manager.close(session.session_id) is True
    await browser_manager.close_all()

    import httpx
    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        navigated = await client.post("/api/v1/browser/navigate", json={"url": "https://example.com"})
        assert navigated.status_code == 200, navigated.text
        api_session_id = navigated.json()["result"]["session"]["session_id"]
        scraped = await client.post(f"/api/v1/browser/session/{api_session_id}/scrape")
        assert scraped.status_code == 200, scraped.text
        assert "Example Domain" in scraped.json()["result"]["text"]
        closed = await client.post(f"/api/v1/browser/session/{api_session_id}/close")
        assert closed.status_code == 200, closed.text

    await browser_manager.close_all()
    print("browser foundation checks passed")


if __name__ == "__main__":
    asyncio.run(main())
