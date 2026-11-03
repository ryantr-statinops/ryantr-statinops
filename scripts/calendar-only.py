"""Keep only the calendar from the pinned github-profile-3d-contrib SVG."""

import argparse
from pathlib import Path
import re
import xml.etree.ElementTree as ET


SVG = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG)


def calendar_only(source: Path, destination: Path) -> None:
    root = ET.parse(source).getroot()
    calendars = [
        group for group in root.findall(f"{{{SVG}}}g")
        if any(
            rect.get("class", "").startswith("cont-top-")
            for rect in group.iter(f"{{{SVG}}}rect")
        )
    ]
    if len(calendars) != 1:
        raise ValueError("Expected exactly one 3D calendar; upstream SVG may have changed")
    calendar = calendars[0]
    bars = calendar.findall(f"{{{SVG}}}g")
    top_positions = []
    for bar in bars:
        match = re.fullmatch(r"translate\(([-\d.]+) ([-\d.]+)\)", bar.get("transform", ""))
        if not match:
            raise ValueError("Unexpected calendar bar transform")
        top_positions.append(float(match[2]))
    if not top_positions:
        raise ValueError("The contribution calendar is empty")

    width, original_height = float(root.get("width")), float(root.get("height"))
    # The top face extends above each bar origin. Keep padding for the faces
    # and the final row, while removing the empty space reserved for other charts.
    top = min(top_positions) - 32
    height = original_height + 32 - top
    for child in list(root):
        if child is not calendar and child.tag not in {f"{{{SVG}}}style", f"{{{SVG}}}defs"}:
            root.remove(child)

    background = ET.Element(f"{{{SVG}}}rect", {
        "x": "0", "y": f"{top:.2f}", "width": f"{width:g}",
        "height": f"{height:.2f}", "class": "fill-bg",
    })
    root.insert(list(root).index(calendar), background)
    root.set("height", f"{height:.2f}")
    root.set("viewBox", f"0 {top:.2f} {width:g} {height:.2f}")
    root.set("role", "img")
    root.set("aria-labelledby", "calendar-title calendar-description")
    title = ET.Element(f"{{{SVG}}}title", {"id": "calendar-title"})
    title.text = "Ryan's GitHub contribution calendar"
    description = ET.Element(f"{{{SVG}}}desc", {"id": "calendar-description"})
    description.text = "Daily contributions over the past year. Taller cyan blocks indicate more activity."
    root.insert(0, title)
    root.insert(1, description)
    destination.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(destination, encoding="utf-8", xml_declaration=True)
    print(f"Saved {destination}: {len(bars)} days, calendar only")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    arguments = parser.parse_args()
    calendar_only(arguments.source, arguments.destination)
