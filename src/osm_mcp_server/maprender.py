"""Static map rendering from OSM-style raster tiles (Web Mercator, 256px tiles)."""

import asyncio
import io
import math
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import aiohttp
from PIL import Image, ImageColor, ImageDraw, ImageFont

TILE_SIZE = 256
MAX_ZOOM = 19
MAX_DIM = 2400
MAX_TILES = 100
CACHE_MAX_AGE = 7 * 24 * 3600
ATTRIBUTION = "\u00a9 OpenStreetMap contributors"
ALLOWED_EXTENSIONS = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG"}

TILE_URL = os.environ.get("OSM_MCP_TILE_URL", "https://tile.openstreetmap.org/{z}/{x}/{y}.png")
USER_AGENT = os.environ.get(
    "OSM_MCP_USER_AGENT",
    "osm-mcp-server/0.2 (+https://github.com/toughIQ/open-streetmap-mcp)",
)
CACHE_DIR = Path(os.environ.get("OSM_MCP_CACHE_DIR", "~/.cache/osm-mcp-server/tiles")).expanduser()

_tile_semaphore: Optional[asyncio.Semaphore] = None


def _semaphore() -> asyncio.Semaphore:
    # OSM tile usage policy: max 2 concurrent connections
    global _tile_semaphore
    if _tile_semaphore is None:
        _tile_semaphore = asyncio.Semaphore(2)
    return _tile_semaphore


def world_px(lat: float, lon: float, zoom: int) -> Tuple[float, float]:
    lat = max(min(lat, 85.0511287798), -85.0511287798)
    n = TILE_SIZE * (2 ** zoom)
    x = (lon + 180.0) / 360.0 * n
    y = (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n
    return x, y


def world_to_latlon(x: float, y: float, zoom: int) -> Tuple[float, float]:
    n = TILE_SIZE * (2 ** zoom)
    lon = x / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    return lat, lon


def fit_zoom(points: Sequence[Tuple[float, float]], width: int, height: int, padding: int = 40) -> int:
    """Highest zoom at which all (lat, lon) points fit inside the image minus padding."""
    for zoom in range(MAX_ZOOM, -1, -1):
        xs, ys = zip(*(world_px(lat, lon, zoom) for lat, lon in points))
        if max(xs) - min(xs) <= width - 2 * padding and max(ys) - min(ys) <= height - 2 * padding:
            return zoom
    return 0


def center_of(points: Sequence[Tuple[float, float]], zoom: int) -> Tuple[float, float]:
    xs, ys = zip(*(world_px(lat, lon, zoom) for lat, lon in points))
    return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2


def _cache_path(url_template: str, z: int, x: int, y: int) -> Path:
    host = url_template.split("//", 1)[-1].split("/", 1)[0].replace(":", "_")
    return CACHE_DIR / host / str(z) / str(x) / f"{y}.png"


async def _fetch_tile(session: aiohttp.ClientSession, z: int, x: int, y: int) -> bytes:
    x %= 2 ** z
    path = _cache_path(TILE_URL, z, x, y)
    if path.exists() and time.time() - path.stat().st_mtime < CACHE_MAX_AGE:
        return path.read_bytes()

    url = TILE_URL.format(z=z, x=x, y=y)
    last_error: Optional[Exception] = None
    for attempt in range(2):
        try:
            async with _semaphore():
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.read()
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(data)
                        return data
                    last_error = RuntimeError(f"HTTP {response.status}")
        except aiohttp.ClientError as e:
            last_error = e
        await asyncio.sleep(1 + attempt)
    raise RuntimeError(f"Failed to fetch tile {z}/{x}/{y}: {last_error}")


def _font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _color(value: Optional[str], default: str) -> Tuple[int, int, int]:
    try:
        return ImageColor.getrgb(value or default)[:3]
    except ValueError:
        return ImageColor.getrgb(default)[:3]


def normalize_route(route: Any) -> List[Tuple[float, float]]:
    """Accept a GeoJSON LineString dict or a list of [lon, lat] pairs; return (lat, lon) tuples."""
    if route is None:
        return []
    if isinstance(route, dict):
        route = route.get("coordinates", [])
    return [(float(c[1]), float(c[0])) for c in route if len(c) >= 2]


def _draw_overlay(
    size: Tuple[int, int],
    to_view,
    markers: List[Dict[str, Any]],
    route: List[Tuple[float, float]],
    route_color: str,
) -> Image.Image:
    scale = 2  # supersample for smooth lines
    overlay = Image.new("RGBA", (size[0] * scale, size[1] * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    if len(route) >= 2:
        pts = [tuple(v * scale for v in to_view(lat, lon)) for lat, lon in route]
        draw.line(pts, fill=(255, 255, 255, 230), width=9 * scale, joint="curve")
        draw.line(pts, fill=_color(route_color, "#1a73e8") + (255,), width=5 * scale, joint="curve")

    label_font = _font(14 * scale)
    text_font = _font(15 * scale)
    for marker in markers:
        px, py = (v * scale for v in to_view(marker["latitude"], marker["longitude"]))
        text = marker.get("text")
        r = (12 if text else 9) * scale
        fill = _color(marker.get("color"), "#d93025")
        draw.ellipse((px - r - 2 * scale, py - r - 2 * scale, px + r + 2 * scale, py + r + 2 * scale), fill=(255, 255, 255, 255))
        draw.ellipse((px - r, py - r, px + r, py + r), fill=fill + (255,))
        if text:
            draw.text((px, py), str(text), font=text_font, fill=(255, 255, 255, 255), anchor="mm")
        else:
            draw.ellipse((px - 3 * scale, py - 3 * scale, px + 3 * scale, py + 3 * scale), fill=(255, 255, 255, 255))
        label = marker.get("label")
        if label:
            draw.text(
                (px + r + 6 * scale, py),
                str(label),
                font=label_font,
                fill=(20, 20, 20, 255),
                anchor="lm",
                stroke_width=2 * scale,
                stroke_fill=(255, 255, 255, 255),
            )

    return overlay.resize(size, Image.LANCZOS)


def _draw_attribution(image: Image.Image) -> None:
    draw = ImageDraw.Draw(image, "RGBA")
    font = _font(11)
    left, top, right, bottom = draw.textbbox((0, 0), ATTRIBUTION, font=font)
    w, h = right - left, bottom - top
    x0, y0 = image.width - w - 10, image.height - h - 8
    draw.rectangle((x0 - 4, y0 - 3, image.width, image.height), fill=(255, 255, 255, 200))
    draw.text((x0, y0 - top), ATTRIBUTION, font=font, fill=(40, 40, 40, 255))


def _compose(
    tiles: Dict[Tuple[int, int], bytes],
    zoom: int,
    origin: Tuple[float, float],
    size: Tuple[int, int],
    markers: List[Dict[str, Any]],
    route: List[Tuple[float, float]],
    route_color: str,
) -> Image.Image:
    ox, oy = origin
    tx0, ty0 = int(ox // TILE_SIZE), int(oy // TILE_SIZE)
    tx1, ty1 = int((ox + size[0] - 1) // TILE_SIZE), int((oy + size[1] - 1) // TILE_SIZE)
    canvas = Image.new("RGB", ((tx1 - tx0 + 1) * TILE_SIZE, (ty1 - ty0 + 1) * TILE_SIZE), (221, 221, 221))
    for (tx, ty), data in tiles.items():
        with Image.open(io.BytesIO(data)) as tile:
            canvas.paste(tile.convert("RGB"), ((tx - tx0) * TILE_SIZE, (ty - ty0) * TILE_SIZE))

    left, top = int(ox - tx0 * TILE_SIZE), int(oy - ty0 * TILE_SIZE)
    image = canvas.crop((left, top, left + size[0], top + size[1])).convert("RGBA")

    def to_view(lat: float, lon: float) -> Tuple[float, float]:
        x, y = world_px(lat, lon, zoom)
        return x - ox, y - oy

    image.alpha_composite(_draw_overlay(size, to_view, markers, route, route_color))
    _draw_attribution(image)
    return image.convert("RGB")


async def render(
    output_path: str,
    width: int = 800,
    height: int = 600,
    center: Optional[Tuple[float, float]] = None,
    zoom: Optional[int] = None,
    bbox: Optional[Tuple[float, float, float, float]] = None,
    markers: Optional[List[Dict[str, Any]]] = None,
    route: Any = None,
    route_color: str = "#1a73e8",
) -> Dict[str, Any]:
    """Render a map. bbox is (min_lat, min_lon, max_lat, max_lon). Returns a summary dict."""
    markers = [dict(m) for m in (markers or [])]
    for m in markers:
        if "latitude" not in m or "longitude" not in m:
            raise ValueError("Each marker needs 'latitude' and 'longitude'")
        m["latitude"], m["longitude"] = float(m["latitude"]), float(m["longitude"])
    route_pts = normalize_route(route)

    if not (64 <= width <= MAX_DIM and 64 <= height <= MAX_DIM):
        raise ValueError(f"width and height must be between 64 and {MAX_DIM}")

    out = Path(output_path).expanduser()
    fmt = ALLOWED_EXTENSIONS.get(out.suffix.lower())
    if not fmt:
        raise ValueError("output_path must end in .png, .jpg or .jpeg")

    content_pts = [(m["latitude"], m["longitude"]) for m in markers] + route_pts
    if bbox:
        min_lat, min_lon, max_lat, max_lon = bbox
        fit_pts = [(min_lat, min_lon), (max_lat, max_lon)]
        zoom = zoom if zoom is not None else fit_zoom(fit_pts, width, height)
        cx, cy = center_of(fit_pts, zoom)
    elif center:
        zoom = zoom if zoom is not None else 15
        cx, cy = world_px(center[0], center[1], zoom)
    elif content_pts:
        zoom = zoom if zoom is not None else (fit_zoom(content_pts, width, height) if len(content_pts) > 1 else 15)
        cx, cy = center_of(content_pts, zoom)
    else:
        raise ValueError("Provide a center (latitude/longitude), a bounding box, or markers/route to fit")

    zoom = max(0, min(int(zoom), MAX_ZOOM))
    origin = (cx - width / 2, cy - height / 2)
    n = 2 ** zoom
    tx0, ty0 = int(origin[0] // TILE_SIZE), int(origin[1] // TILE_SIZE)
    tx1, ty1 = int((origin[0] + width - 1) // TILE_SIZE), int((origin[1] + height - 1) // TILE_SIZE)
    ty0, ty1 = max(ty0, 0), min(ty1, n - 1)
    coords = [(tx, ty) for tx in range(tx0, tx1 + 1) for ty in range(ty0, ty1 + 1)]
    if len(coords) > MAX_TILES:
        raise ValueError(f"Map needs {len(coords)} tiles (max {MAX_TILES}); reduce size or zoom")

    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(headers={"User-Agent": USER_AGENT}, timeout=timeout) as session:
        results = await asyncio.gather(*(_fetch_tile(session, zoom, tx, ty) for tx, ty in coords))
    tiles = dict(zip(coords, results))

    image = await asyncio.to_thread(_compose, tiles, zoom, origin, (width, height), markers, route_pts, route_color)

    out.parent.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(image.save, out, fmt)

    north_west = world_to_latlon(origin[0], origin[1], zoom)
    south_east = world_to_latlon(origin[0] + width, origin[1] + height, zoom)
    return {
        "output_path": str(out.resolve()),
        "width": width,
        "height": height,
        "zoom": zoom,
        "tiles_used": len(coords),
        "bbox": {
            "min_latitude": round(south_east[0], 6),
            "min_longitude": round(north_west[1], 6),
            "max_latitude": round(north_west[0], 6),
            "max_longitude": round(south_east[1], 6),
        },
        "attribution": ATTRIBUTION + " (already drawn on the image; keep it when publishing)",
    }
