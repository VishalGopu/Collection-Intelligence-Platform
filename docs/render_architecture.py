"""Render the implemented system architecture to docs/architecture_built.png."""

from __future__ import annotations

from math import atan2, cos, sin
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


HERE = Path(__file__).resolve().parent
OUT = HERE / "architecture_built.png"
WIDTH, HEIGHT = 2200, 1380
INK = "#152236"
MUTED = "#53657b"
BLUE = "#2365b1"
TEAL = "#087d77"
PURPLE = "#6d4ab2"
AMBER = "#b26714"
WHITE = "#ffffff"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    roots = [Path("C:/Windows/Fonts"), Path("/usr/share/fonts/truetype/dejavu")]
    names = (["segoeuib.ttf", "DejaVuSans-Bold.ttf"] if bold else
             ["segoeui.ttf", "DejaVuSans.ttf"])
    for root in roots:
        for name in names:
            path = root / name
            if path.is_file():
                return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


image = Image.new("RGB", (WIDTH, HEIGHT), "#f6f8fc")
draw = ImageDraw.Draw(image)


def box(xy, title: str, lines: list[str], color: str, tag: str = "") -> None:
    x1, y1, x2, y2 = xy
    draw.rounded_rectangle((x1 + 5, y1 + 7, x2 + 5, y2 + 7), radius=22, fill="#dae2ed")
    draw.rounded_rectangle(xy, radius=22, fill=WHITE, outline="#d5deea", width=2)
    draw.rounded_rectangle((x1, y1, x2, y1 + 12), radius=7, fill=color)
    draw.text((x1 + 25, y1 + 27), title, font=font(27, True), fill=INK)
    top = y1 + 82
    if tag:
        draw.rounded_rectangle((x1 + 25, top, x1 + 25 + len(tag) * 13, top + 35),
                               radius=12, fill=color)
        draw.text((x1 + 37, top + 6), tag, font=font(17, True), fill=WHITE)
        top += 55
    for line in lines:
        draw.text((x1 + 26, top), line, font=font(19), fill=MUTED)
        top += 37


def arrow(points: list[tuple[int, int]], color: str = BLUE, label: str = "") -> None:
    draw.line(points, fill=color, width=6, joint="curve")
    x1, y1 = points[-2]
    x2, y2 = points[-1]
    angle = atan2(y2 - y1, x2 - x1)
    wings = []
    for offset in (2.55, -2.55):
        wings.append((x2 + 22 * cos(angle + offset), y2 + 22 * sin(angle + offset)))
    draw.polygon([(x2, y2), *wings], fill=color)
    if label:
        mx = (points[0][0] + points[-1][0]) // 2
        my = (points[0][1] + points[-1][1]) // 2 - 27
        draw.text((mx - 10, my), label, font=font(17, True), fill=color)


draw.text((76, 54), "Collection Intelligence Platform", font=font(47, True), fill=INK)
draw.text((78, 119), "Implemented architecture  |  Maple synthetic release, 28 Sep 2026",
          font=font(23), fill=MUTED)

box((72, 255, 420, 565), "Source release", [
    "31 CSV / Parquet tables", "CRM, accounts, cases,", "contacts and promises", "Policies, notes, transcripts",
], BLUE)
box((520, 255, 945, 595), "Layer 1 · C360", [
    "DuckDB normalization", "Rule-based identity matching", "Linked threshold: 0.95", "Parquet gold + crosswalk", "Quality gates and profile",
], TEAL)
box((1025, 220, 1530, 590), "Layer 2 · Questions", [
    "Certified SQL in DuckDB", "Deterministic question routes", "Document / transcript sources", "SQLGlot read-only validation", "Groq or OpenAI LLM fallback",
], PURPLE, "AI: optional SQL planning")
box((1025, 710, 1530, 1080), "Layers 3/4 · Decisioning", [
    "Point-in-time + text rules", "LightGBM promise model + SHAP", "Policy gate and action ranking", "Support case specialist route", "Proposal saved before review",
], AMBER, "AI: LightGBM + SHAP")
box((1640, 255, 2120, 655), "Streamlit app", [
    "Customer: linked C360 records", "Ask: global or linked scope", "Recommendation + policy blocks", "Worklist: ranked promises", "SQL / sources on every answer",
], BLUE)
box((1640, 790, 2120, 1040), "Human review", [
    "Approve / modify / reject", "Policy rechecked on review", "No automated customer contact",
], TEAL, "HUMAN DECISION")
box((1640, 1130, 2120, 1300), "Audit trail", [
    "SQLite decisions + review events", "Recent rows shown in Streamlit",
], PURPLE)

arrow([(420, 380), (520, 380)], BLUE)
arrow([(420, 520), (475, 520), (475, 740), (1025, 740)], AMBER)
arrow([(735, 255), (735, 190), (1850, 190), (1850, 255)], TEAL)
draw.text((1180, 157), "gold + linked crosswalk", font=font(18, True), fill=TEAL)
arrow([(945, 380), (1025, 380)], TEAL)
arrow([(945, 540), (980, 540), (980, 930), (1025, 930)], TEAL)
arrow([(1530, 385), (1640, 385)], PURPLE)
arrow([(1530, 870), (1590, 870), (1590, 565), (1640, 565)], AMBER)
arrow([(1880, 655), (1880, 790)], TEAL)
arrow([(1880, 1040), (1880, 1130)], PURPLE)

draw.text((74, 1170), "Current boundary", font=font(23, True), fill=INK)
draw.text((74, 1210), "Customer-scoped Ask uses a narrow linked-crosswalk route; unsupported filters are refused.",
          font=font(20), fill=MUTED)
draw.text((74, 1245), "Offline text rules supply context; unknown safe questions may use LLM SQL planning; no live contact.",
          font=font(20), fill=MUTED)

image.save(OUT, optimize=True)
print(OUT)
