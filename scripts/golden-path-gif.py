#!/usr/bin/env python3
"""Assemble docs/images/golden-path.gif from real frames of the self-service path.

Frame 1 is the terminal (rendered text, the real output of the first request
on 2026-10-24); the others are screenshots taken by scripts/screenshots.py and
headless Edge. Runs inside the devcontainer (Pillow in agents/.venv):

    agents/.venv/bin/python scripts/golden-path-gif.py docs/images
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH = 1000
FRAME_MS = 2200

TERMINAL = [
    ("$ platform request s3-bucket --name demo-uploads --team web --cost-center cc-100", "cmd"),
    ("request r-60c80a: s3-bucket demo-uploads -> pr-opened", ""),
    ("pull request: https://github.com/asaf-1/DevOps-Platform/pull/2", ""),
    ("", ""),
    ("$ platform status r-60c80a", "cmd"),
    ("  19:22:10  requested   vscode (human)", ""),
    ("  19:22:14  pr-opened   platform-api (system)   pull/2", ""),
    ("  19:24:55  plan-ok     github-actions/iac-pr    6 to add, 0 to change, 0 to destroy", ""),
    ("  19:24:55  policy-ok   github-actions/iac-pr    conftest terraform-default: passed", ""),
    ("  19:24:55  planned     apply-worker (system)", ""),
    ("  19:41:29  approved    github/iac-approve (human)   asaf-1", ""),
    ("  19:58:26  applied     apply-worker (system)   bucket_name demo-uploads", ""),
    ("  19:58:27  deployed    apply-worker (system)   ConfigMap commit 88effad", ""),
]

CAPTIONS = {
    "terminal": "1. One command opens a request and its pull request; the timeline is the audit trail",
    "golden-path-2-pull-request.png": "2. CI comments the plan, the policy result, the security scan and the cost on the PR",
    "golden-path-3-approval.png": "3. One human click: the production environment's required reviewer",
    "golden-path-4-demo-app.png": "4. The worker applied it inside the cluster; the demo app reads its new bucket",
}


def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in ("DejaVuSansMono.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def terminal_frame() -> Image.Image:
    img = Image.new("RGB", (WIDTH, 560), (24, 26, 32))
    d = ImageDraw.Draw(img)
    f = font(17)
    y = 28
    for text, kind in TERMINAL:
        colour = (120, 220, 140) if kind == "cmd" else (225, 225, 225)
        d.text((28, y), text, fill=colour, font=f)
        y += 30
    return img


def captioned(img: Image.Image, caption: str) -> Image.Image:
    ratio = WIDTH / img.width
    body = img.resize((WIDTH, int(img.height * ratio)))
    out = Image.new("RGB", (WIDTH, body.height + 54), (255, 255, 255))
    out.paste(body, (0, 54))
    d = ImageDraw.Draw(out)
    d.rectangle([0, 0, WIDTH, 54], fill=(14, 92, 56))
    d.text((18, 15), caption, fill=(255, 255, 255), font=font(20))
    return out


def main(images: Path) -> int:
    frames = [captioned(terminal_frame(), CAPTIONS["terminal"])]
    for name in ("golden-path-2-pull-request.png", "golden-path-3-approval.png", "golden-path-4-demo-app.png"):
        frames.append(captioned(Image.open(images / name).convert("RGB"), CAPTIONS[name]))
    height = max(f.height for f in frames)
    padded = []
    for f in frames:
        canvas = Image.new("RGB", (WIDTH, height), (255, 255, 255))
        canvas.paste(f, (0, 0))
        padded.append(canvas.quantize(colors=128))
    out = images / "golden-path.gif"
    padded[0].save(out, save_all=True, append_images=padded[1:], duration=FRAME_MS, loop=0, optimize=True)
    print("wrote", out, out.stat().st_size, "bytes,", len(padded), "frames")
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1] if len(sys.argv) > 1 else "docs/images")))
