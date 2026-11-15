"""Route step text (en/de), step merging and printable A4 PDF route sheets."""

import html
from datetime import datetime
from typing import Any, Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image as RLImage
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

COLOR_START = "#1e8e3e"
COLOR_END = "#d93025"
COLOR_STEP = "#174ea6"

COMPASS = {
    "en": ["north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest"],
    "de": ["Norden", "Nordosten", "Osten", "Südosten", "Süden", "Südwesten", "Westen", "Nordwesten"],
}

MODIFIERS = {
    "en": {"left": "left", "right": "right", "slight left": "slight left", "slight right": "slight right",
           "sharp left": "sharp left", "sharp right": "sharp right", "straight": "straight", "uturn": "around"},
    "de": {"left": "links", "right": "rechts", "slight left": "leicht links", "slight right": "leicht rechts",
           "sharp left": "scharf links", "sharp right": "scharf rechts", "straight": "geradeaus", "uturn": "um"},
}

T = {
    "en": {
        "unnamed_path": "an unnamed path", "unnamed_road": "an unnamed road",
        "onto": " onto {}", "on": " on {}",
        "depart": "Head {heading}{on}",
        "arrive": "Arrive at your destination{side}{on}",
        "side_left": " (on the left)", "side_right": " (on the right)",
        "roundabout_exit": "At the roundabout take exit {n}{onto}", "roundabout": "Enter the roundabout{onto}",
        "exit_roundabout": "Exit the roundabout{onto}",
        "merge": "Merge {mod}{onto}", "ramp": "Take the ramp {mod}{onto}", "fork": "Keep {mod} at the fork{onto}",
        "uturn": "Make a U-turn{onto}", "straight": "Continue straight{onto}", "turn": "Turn {mod}{onto}",
        "continue_mod": "Continue {mod}{onto}",
        "cross": "Follow the short unnamed connections (about {dist})",
        "then": "then {dist}",
        "mode": {"foot": "Walking route", "bike": "Cycling route", "car": "Driving route"},
        "from": "From", "to": "To", "distance": "Distance", "time": "Time (estimate)",
        "no": "No.", "directions": "Directions", "walk": "Distance to next point",
        "minutes": "about {n} min",
        "detail": "Detail of the crowded section (numbers as above)",
        "arrival_street": "The route ends on {street}, the nearest street to the destination.",
        "snap": "The destination is about {n} m from the end of the route.",
        "no_housenumber": "no house number in OpenStreetMap",
        "footer": "Map data (c) OpenStreetMap contributors (ODbL). Routing: OSRM by FOSSGIS. Created {date}. Times and unnamed paths are estimates, check on site.",
    },
    "de": {
        "unnamed_path": "einen namenlosen Weg", "unnamed_road": "eine namenlose Straße",
        "onto": " auf {}", "on": " auf {}",
        "depart": "Gehen Sie Richtung {heading}{on}",
        "arrive": "Ziel erreicht{side}{on}",
        "side_left": " (links)", "side_right": " (rechts)",
        "roundabout_exit": "Im Kreisverkehr die {n}. Ausfahrt nehmen{onto}", "roundabout": "In den Kreisverkehr einfahren{onto}",
        "exit_roundabout": "Kreisverkehr verlassen{onto}",
        "merge": "Einfädeln {mod}{onto}", "ramp": "Rampe nehmen {mod}{onto}", "fork": "An der Gabelung {mod} halten{onto}",
        "uturn": "Wenden{onto}", "straight": "Geradeaus weiter{onto}", "turn": "{Mod} abbiegen{onto}",
        "continue_mod": "Weiter {mod}{onto}",
        "cross": "Den kurzen namenlosen Wegstücken folgen (ca. {dist})",
        "then": "danach {dist}",
        "mode": {"foot": "Fußweg", "bike": "Radroute", "car": "Autoroute"},
        "from": "Von", "to": "Nach", "distance": "Strecke", "time": "Dauer (Schätzung)",
        "no": "Nr.", "directions": "Wegbeschreibung", "walk": "Strecke bis zum nächsten Punkt",
        "minutes": "ca. {n} Min.",
        "detail": "Detailausschnitt des engen Abschnitts (Nummern wie oben)",
        "arrival_street": "Die Route endet in der {street}, der nächsten Straße zum Ziel.",
        "snap": "Das Ziel liegt etwa {n} m vom Routenende entfernt.",
        "no_housenumber": "keine Hausnummer in OpenStreetMap",
        "footer": "Kartendaten (c) OpenStreetMap-Mitwirkende (ODbL). Routing: OSRM von FOSSGIS. Erstellt am {date}. Zeiten und namenlose Wege sind Schätzungen, bitte vor Ort prüfen.",
    },
}


def fmt_dist(meters: float, lang: str = "en") -> str:
    text = f"{int(round(meters))} m" if meters < 1000 else f"{meters / 1000:.1f} km"
    return text.replace(".", ",") if lang == "de" else text


def fmt_minutes(seconds: float, lang: str = "en") -> str:
    return T[lang]["minutes"].format(n=max(1, int(round(seconds / 60))))


def describe_step(step: Dict[str, Any], lang: str = "en", mode: str = "foot") -> str:
    """Build a readable instruction from an OSRM step (OSRM does not provide text itself)."""
    t = T[lang]
    maneuver = step.get("maneuver", {})
    kind = maneuver.get("type", "")
    modifier = maneuver.get("modifier", "")
    mod = MODIFIERS[lang].get(modifier, modifier)
    name = step.get("name") or ""
    unnamed = t["unnamed_path"] if mode in ("foot", "bike") else t["unnamed_road"]
    onto = t["onto"].format(name or unnamed)
    onto_named = t["onto"].format(name) if name else ""

    if kind == "depart":
        bearing = maneuver.get("bearing_after")
        heading = COMPASS[lang][int(((bearing + 22.5) % 360) // 45)] if bearing is not None else ""
        text = t["depart"].format(heading=heading, on=t["on"].format(name) if name else "")
        return text.replace("  ", " ").strip()
    if kind == "arrive":
        side = t["side_left"] if modifier == "left" else t["side_right"] if modifier == "right" else ""
        return t["arrive"].format(side=side, on=t["on"].format(name) if name else "")
    if kind in ("roundabout", "rotary", "roundabout turn"):
        exit_no = maneuver.get("exit")
        return t["roundabout_exit"].format(n=exit_no, onto=onto_named) if exit_no else t["roundabout"].format(onto=onto_named)
    if kind in ("exit roundabout", "exit rotary"):
        return t["exit_roundabout"].format(onto=onto_named)
    if kind == "merge":
        return t["merge"].format(mod=mod, onto=onto_named).replace("  ", " ")
    if kind in ("on ramp", "off ramp"):
        return t["ramp"].format(mod=mod, onto=onto_named).replace("  ", " ")
    if kind == "fork":
        return t["fork"].format(mod=mod, onto=onto_named).replace("  ", " ")
    if kind in ("turn", "end of road"):
        if modifier == "uturn":
            return t["uturn"].format(onto=onto)
        if modifier == "straight":
            return t["straight"].format(onto=onto)
        return t["turn"].format(mod=mod, Mod=mod.capitalize(), onto=onto)
    if kind in ("continue", "new name"):
        if modifier in ("", "straight"):
            return t["straight"].format(onto=onto_named)
        return t["continue_mod"].format(mod=mod, onto=onto_named)
    return f"{kind} {mod}".strip().capitalize() + onto_named


def build_steps(route: Dict[str, Any], lang: str = "en", mode: str = "foot") -> List[Dict[str, Any]]:
    """Readable, labelled steps. Runs of tiny unnamed steps are merged. First is A, last is B."""
    t = T[lang]
    raw: List[Dict[str, Any]] = []
    for leg in route.get("legs", []):
        for s in leg.get("steps", []):
            m = s.get("maneuver", {})
            raw.append({
                "kind": m.get("type", ""),
                "name": s.get("name") or "",
                "distance": float(s.get("distance", 0.0)),
                "duration": float(s.get("duration", 0.0)),
                "location": m.get("location"),
                "text": describe_step(s, lang, mode),
            })

    def tiny(x: Dict[str, Any]) -> bool:
        return not x["name"] and x["distance"] < 30 and x["kind"] not in ("depart", "arrive")

    merged: List[Dict[str, Any]] = []
    i = 0
    while i < len(raw):
        if tiny(raw[i]):
            j = i
            while j < len(raw) and tiny(raw[j]):
                j += 1
            if j - i >= 2:
                run = raw[i:j]
                dist = sum(r["distance"] for r in run)
                merged.append({
                    "kind": "cross", "name": "", "distance": dist,
                    "duration": sum(r["duration"] for r in run), "location": run[0]["location"],
                    "text": t["cross"].format(dist=fmt_dist(dist, lang)),
                })
                i = j
                continue
        merged.append(raw[i])
        i += 1

    number = 0
    for idx, step in enumerate(merged):
        if idx == 0:
            step["label"] = "A"
        elif idx == len(merged) - 1:
            step["label"] = "B"
        else:
            number += 1
            step["label"] = str(number)
    return merged


def arrival_note(arrival_street: str, dest_road: Optional[str], snap_m: Optional[float], lang: str) -> str:
    t = T[lang]
    notes = []
    if arrival_street and dest_road and arrival_street != dest_road:
        notes.append(t["arrival_street"].format(street=arrival_street))
    if snap_m is not None and snap_m > 30:
        notes.append(t["snap"].format(n=int(round(snap_m))))
    return " ".join(notes)


def _txt(value: Any) -> str:
    """Escape for reportlab Paragraph and keep to characters the built-in Helvetica can show."""
    text = str(value).encode("cp1252", "replace").decode("cp1252")
    return html.escape(text)


def build_pdf(
    path: str,
    map_image: str,
    map_size: tuple,
    title: str,
    lang: str,
    mode: str,
    distance_m: float,
    duration_s: float,
    start: Dict[str, str],
    end: Dict[str, str],
    steps: List[Dict[str, Any]],
    detail_image: Optional[str] = None,
    detail_size: Optional[tuple] = None,
) -> None:
    t = T[lang]
    base = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=base["Title"], fontSize=17, leading=21, alignment=0, spaceAfter=2)
    sub = ParagraphStyle("sub", parent=base["Normal"], fontSize=10, textColor=colors.HexColor("#444444"), spaceAfter=6)
    body = ParagraphStyle("body", parent=base["Normal"], fontSize=9.5, leading=12)
    small = ParagraphStyle("small", parent=body, fontSize=8.5, leading=10.5, textColor=colors.HexColor("#555555"))
    cell_white = ParagraphStyle("cw", parent=body, textColor=colors.white, alignment=1, fontName="Helvetica-Bold", fontSize=10)

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#666666"))
        canvas.drawString(15 * mm, 9 * mm, _txt_plain(t["footer"].format(date=datetime.now().strftime("%d.%m.%Y"))))
        canvas.restoreState()

    def _txt_plain(value: str) -> str:
        return value.replace("(c)", "\u00a9").encode("cp1252", "replace").decode("cp1252")

    width = 180 * mm
    story: List[Any] = [
        Paragraph(_txt(title), h1),
        Paragraph(_txt(f"{t['mode'][mode]}: {fmt_dist(distance_m, lang)}, {fmt_minutes(duration_s, lang)}"), sub),
        RLImage(map_image, width=width, height=width * map_size[1] / map_size[0]),
        Spacer(1, 4 * mm),
    ]

    def place_cell(info: Dict[str, str]) -> Paragraph:
        text = f"<b>{_txt(info['name'])}</b><br/>{_txt(info['address'])}"
        if info.get("note"):
            text += f"<br/><font size=8 color='#555555'>{_txt(info['note'])}</font>"
        return Paragraph(text, body)

    places = Table(
        [[Paragraph("A", cell_white), Paragraph(f"<b>{_txt(t['from'])}</b>", body), place_cell(start)],
         [Paragraph("B", cell_white), Paragraph(f"<b>{_txt(t['to'])}</b>", body), place_cell(end)]],
        colWidths=[10 * mm, 18 * mm, 152 * mm],
    )
    places.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), colors.HexColor(COLOR_START)),
        ("BACKGROUND", (0, 1), (0, 1), colors.HexColor(COLOR_END)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.4, colors.HexColor("#cccccc")),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story += [places, Spacer(1, 5 * mm)]
    if detail_image and detail_size:
        story += [
            KeepTogether([
                Paragraph(_txt(t["detail"]), small),
                Spacer(1, 1.5 * mm),
                RLImage(detail_image, width=width, height=width * detail_size[1] / detail_size[0]),
            ]),
            Spacer(1, 5 * mm),
        ]

    rows = [[Paragraph(f"<b>{_txt(t['no'])}</b>", body), Paragraph(f"<b>{_txt(t['directions'])}</b>", body),
             Paragraph(f"<b>{_txt(t['walk'])}</b>", body)]]
    styles = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eaed")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#dddddd")),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    for idx, step in enumerate(steps, start=1):
        label = step["label"]
        color = COLOR_START if label == "A" else COLOR_END if label == "B" else COLOR_STEP
        dist = "" if label == "B" else _txt(fmt_dist(step["distance"], lang))
        rows.append([Paragraph(_txt(label), cell_white), Paragraph(_txt(step["text"]), body), Paragraph(dist, body)])
        styles.append(("BACKGROUND", (0, idx), (0, idx), colors.HexColor(color)))
    steps_table = Table(rows, colWidths=[14 * mm, 126 * mm, 40 * mm], repeatRows=1)
    steps_table.setStyle(TableStyle(styles))
    story.append(steps_table)

    doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
                            topMargin=14 * mm, bottomMargin=16 * mm, title=title, author="osm-mcp-server")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
