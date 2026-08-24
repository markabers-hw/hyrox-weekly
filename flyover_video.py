"""Generate a vertical (9:16) flyover video of a newsletter edition.

Scrolls the rendered newsletter HTML from top to bottom, then shows an
animated stats ticker that counts up to the total YouTube / podcast /
article counts for the edition.
"""

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from playwright.async_api import async_playwright

VIEWPORT = {"width": 1080, "height": 1920}
SCROLL_SECONDS = 12
STATS_TICK_SECONDS = 3
STATS_HOLD_SECONDS = 3
FPS = 30


STATS_OVERLAY_JS = r"""
(function (counts) {
  return new Promise((resolve) => {
    const style = document.createElement('style');
    style.textContent = `
      @keyframes flyoverPulse { 0%,100% { transform: scale(1); opacity:1 } 50% { transform: scale(1.06); opacity:.75 } }
      #flyover-stats-overlay .flyover-accent { animation: flyoverPulse 1.6s ease-in-out infinite; transform-origin:center }
    `;
    document.head.appendChild(style);

    const root = document.createElement('div');
    root.id = 'flyover-stats-overlay';
    root.style.cssText = [
      'position:fixed','inset:0','background:#1a1a1a','color:#fff',
      'display:flex','flex-direction:column','align-items:center','justify-content:center',
      'font-family:Barlow,sans-serif','z-index:2147483647','opacity:0',
      'transition:opacity 400ms ease','padding:80px 60px','text-align:center',
    ].join(';');

    root.innerHTML = `
      <div class="flyover-accent" style="font-size:28px;letter-spacing:6px;color:#CC5500;font-weight:700;margin-bottom:24px;text-transform:uppercase">This Week</div>
      <div style="font-size:56px;font-weight:800;letter-spacing:2px;margin-bottom:80px;line-height:1.1">HYROX WEEKLY</div>
      <div id="flyover-stats-grid" style="display:flex;flex-direction:column;gap:56px;width:100%;max-width:760px">
        ${counts.map((row) => `
          <div style="display:flex;align-items:baseline;justify-content:space-between;border-bottom:2px solid rgba(255,255,255,0.12);padding-bottom:24px">
            <div style="font-size:34px;font-weight:600;letter-spacing:4px;text-transform:uppercase;color:#aaa">${row.label}</div>
            <div class="flyover-num" data-target="${row.value}" style="font-size:140px;font-weight:800;color:#fff;font-variant-numeric:tabular-nums;line-height:1">0</div>
          </div>
        `).join('')}
      </div>
      <div style="margin-top:80px;font-size:24px;letter-spacing:3px;color:#888;text-transform:uppercase">hyroxweekly.com</div>
    `;
    document.body.appendChild(root);
    requestAnimationFrame(() => { root.style.opacity = '1'; });

    const tickMs = 3000;
    const holdMs = 3000;
    const nums = Array.from(root.querySelectorAll('.flyover-num'));
    const start = performance.now();
    function step(now) {
      const t = Math.min((now - start) / tickMs, 1);
      // ease-out cubic
      const eased = 1 - Math.pow(1 - t, 3);
      nums.forEach((el) => {
        const target = parseInt(el.dataset.target, 10) || 0;
        el.textContent = Math.round(target * eased).toString();
      });
      if (t < 1) requestAnimationFrame(step);
      else setTimeout(resolve, holdMs);
    }
    requestAnimationFrame(step);
  });
})
"""


async def _record(html_path: str, counts: list, output_webm_dir: str) -> str:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context(
            viewport=VIEWPORT,
            device_scale_factor=1,
            record_video_dir=output_webm_dir,
            record_video_size=VIEWPORT,
        )
        page = await context.new_page()
        await page.goto(f"file://{html_path}")
        await page.wait_for_load_state("networkidle")
        # Tiny settle so first frame is fully painted
        await page.wait_for_timeout(250)

        total_height = await page.evaluate("document.documentElement.scrollHeight")
        scroll_distance = max(0, total_height - VIEWPORT["height"])

        # Drive the scroll from Python so Playwright captures a frame at every
        # step. Headless Chromium throttles in-page requestAnimationFrame in a
        # way that lets the JS animation finish in real-time but only emits a
        # tiny number of frames to the video stream, which makes the scroll
        # look like an instant jump.
        steps = SCROLL_SECONDS * 30  # ~30 logical fps
        for i in range(steps + 1):
            p = i / steps if steps else 1
            if p < 0.85:
                eased = p / 0.85 * 0.92
            else:
                q = (p - 0.85) / 0.15
                eased = 0.92 + (1 - (1 - q) ** 3) * 0.08
            y = int(scroll_distance * eased)
            await page.evaluate("y => window.scrollTo(0, y)", y)
            await page.wait_for_timeout(int(1000 / 30))

        # Hold at the bottom for a beat before stats overlay
        await page.wait_for_timeout(600)

        await page.evaluate(STATS_OVERLAY_JS, counts)
        # JS resolves after tick + hold; give Playwright a margin to capture
        await page.wait_for_timeout((STATS_TICK_SECONDS + STATS_HOLD_SECONDS) * 1000 + 500)

        video = page.video
        await context.close()
        await browser.close()

        webm_path = await video.path() if video else None
        if not webm_path or not os.path.exists(webm_path):
            raise RuntimeError("Playwright did not produce a video file")
        return webm_path


def _transcode_to_mp4(webm_path: str, mp4_path: str) -> None:
    cmd = [
        "ffmpeg", "-y",
        "-i", webm_path,
        "-vf", f"scale={VIEWPORT['width']}:{VIEWPORT['height']}:flags=lanczos,fps={FPS}",
        "-vsync", "cfr",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-an",
        mp4_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr[-2000:]}")


def generate_flyover(html_path: str, counts: list, output_mp4: str) -> str:
    """Render the newsletter HTML as a vertical flyover video.

    counts: list of {"label": str, "value": int} dicts displayed in the
    ticker, in order. Typical: YouTube / Podcasts / Articles.
    """
    if not os.path.isabs(html_path):
        html_path = os.path.abspath(html_path)
    if not os.path.exists(html_path):
        raise FileNotFoundError(html_path)

    with tempfile.TemporaryDirectory(prefix="flyover_") as tmp:
        webm = asyncio.run(_record(html_path, counts, tmp))
        _transcode_to_mp4(webm, output_mp4)
    return output_mp4


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("html", help="path to newsletter HTML")
    parser.add_argument("out", help="output mp4 path")
    parser.add_argument("--youtube", type=int, default=0)
    parser.add_argument("--podcast", type=int, default=0)
    parser.add_argument("--article", type=int, default=0)
    args = parser.parse_args()

    counts = [
        {"label": "YouTube", "value": args.youtube},
        {"label": "Podcasts", "value": args.podcast},
        {"label": "Articles", "value": args.article},
    ]
    out = generate_flyover(args.html, counts, args.out)
    print(f"Wrote: {out}")
