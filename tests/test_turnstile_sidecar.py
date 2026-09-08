"""Unit-тесты для модуля turnstile_sidecar.py."""
import pytest
from unittest.mock import patch, AsyncMock
from turnstile_sidecar import solve_turnstile, solve_turnstile_async


def test_turnstile_sidecar_exports():
    assert callable(solve_turnstile)
    assert callable(solve_turnstile_async)


@pytest.mark.asyncio
async def test_turnstile_sidecar_mock_success():
    with patch("patchright.async_api.async_playwright") as mock_pw:
        mock_instance = AsyncMock()
        mock_pw.return_value.__aenter__.return_value = mock_instance
        
        mock_browser = AsyncMock()
        mock_instance.chromium.launch.return_value = mock_browser
        
        mock_ctx = AsyncMock()
        mock_browser.new_context.return_value = mock_ctx
        
        mock_page = AsyncMock()
        mock_ctx.new_page.return_value = mock_page
        
        mock_el = AsyncMock()
        mock_el.get_attribute.return_value = "0." + "x" * 100
        mock_page.query_selector.return_value = mock_el
        mock_page.frames = []
        
        token = await solve_turnstile_async("https://example.com/test", timeout_sec=2.0)
        assert token is not None
        assert token.startswith("0.")


@pytest.mark.asyncio
async def test_turnstile_sidecar_timeout_returns_none():
    with patch("patchright.async_api.async_playwright") as mock_pw:
        mock_instance = AsyncMock()
        mock_pw.return_value.__aenter__.return_value = mock_instance
        
        mock_browser = AsyncMock()
        mock_instance.chromium.launch.return_value = mock_browser
        
        mock_ctx = AsyncMock()
        mock_browser.new_context.return_value = mock_ctx
        
        mock_page = AsyncMock()
        mock_ctx.new_page.return_value = mock_page
        mock_page.query_selector.return_value = None
        mock_page.frames = []
        
        token = await solve_turnstile_async("https://example.com/test", timeout_sec=1.0)
        assert token is None