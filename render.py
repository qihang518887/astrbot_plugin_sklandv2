"""
Playwright渲染模块 - 将HTML渲染为图片
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("skland_render")

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning("Playwright not installed, image rendering disabled")

TEMPLATE_DIR = Path(__file__).parent / "templates"


class Renderer:
    """Playwright渲染器"""

    _instance: Optional["Renderer"] = None
    _playwright = None
    _browser = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def initialize(self):
        """初始化playwright"""
        if not PLAYWRIGHT_AVAILABLE:
            logger.warning("Playwright not available")
            return False

        if self._playwright is None:
            try:
                self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox"]
                )
                logger.info("Playwright initialized successfully")
                return True
            except Exception as e:
                logger.error(f"Failed to initialize playwright: {e}")
                return False
        return True

    async def close(self):
        """关闭playwright"""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._browser = None
        self._playwright = None
        logger.info("Playwright closed")

    async def render_html(self, html_content: str, viewport: dict = None) -> Optional[bytes]:
        """将HTML渲染为图片"""
        if not await self.initialize():
            return None

        if viewport is None:
            viewport = {"width": 1200, "height": 1}

        try:
            page = await self._browser.new_page(
                viewport=viewport,
                device_scale_factor=1.5
            )
            await page.set_content(html_content, wait_until="networkidle")
            await asyncio.sleep(0.5)

            screenshot = await page.screenshot(type="png", full_page=True)
            await page.close()
            return screenshot
        except Exception as e:
            logger.error(f"Failed to render HTML: {e}")
            return None

    async def render_template(self, template_name: str, context: dict, viewport: dict = None) -> Optional[bytes]:
        """渲染Jinja2模板为图片"""
        try:
            from jinja2 import Environment, FileSystemLoader

            env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
            template = env.get_template(template_name)
            html_content = template.render(**context)
            return await self.render_html(html_content, viewport)
        except Exception as e:
            logger.error(f"Failed to render template: {e}")
            return None


async def render_gacha_history(
    nickname: str,
    server: str,
    avatar_url: str,
    level: int,
    pools: list,
    total_pulls: int = 0,
    six_rate: float = 0.0,
    up_rate: float = 0.0,
) -> Optional[bytes]:
    """渲染抽卡历史记录为图片"""
    renderer = Renderer()
    context = {
        "nickname": nickname,
        "server": server,
        "avatar_url": avatar_url,
        "level": level,
        "pools": pools,
        "total_pulls": total_pulls,
        "six_rate": six_rate,
        "up_rate": up_rate,
    }
    return await renderer.render_template("gacha.html", context, {"width": 800, "height": 1})


renderer = Renderer()