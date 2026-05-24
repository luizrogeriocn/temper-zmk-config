#!/usr/bin/env python3

from __future__ import annotations

import argparse
import copy
import re
import xml.etree.ElementTree as ET
from pathlib import Path


SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
ET.register_namespace("", SVG_NS)
ET.register_namespace("xlink", XLINK_NS)

EXTRA_CSS = """
.overview-section rect.key { fill: #2a2a2a; stroke: #3a3a3a; }
.overview-section rect.key.trans { fill: #232323; opacity: 0.65; }
.overview-section text.label { display: none; }
.overview-default { fill: #f2e4be; font-size: 18px; font-weight: 500; }
.overview-default.small { font-size: 16px; }
.overview-default.thumb-layer { font-size: 14px; }
.overview-default.thumb-layer-num { font-size: 13px; fill: #4a97a6; }
.overview-default.thumb-layer-fun { font-size: 14px; fill: #ffc83d; }
.overview-default-hold { fill: #f2e4be; font-size: 11px; font-weight: 500; dominant-baseline: text-after-edge; }
.overview-num { fill: #4a97a6; font-size: 10px; font-weight: 500; text-anchor: start; dominant-baseline: hanging; }
.overview-fun { fill: #ffc83d; font-size: 10px; font-weight: 500; text-anchor: end; dominant-baseline: hanging; }
.overview-fun.glyph { color: #ffc83d; fill: #ffc83d; }
.section-label { fill: #d0d7de; font-size: 16px; font-weight: 600; text-anchor: start; dominant-baseline: middle; }
"""

LAYER_NAME_MAP = {
    "num_nav_layer": "NAV",
    "default_layer": "DEF",
    "fun_layer": "FUN",
    "game_layer": "GAME",
}

TEXT_MAP = {
    "PRINTSCREEN": "PrtSc",
    "PG UP": "PgUp",
    "PG DN": "PgDn",
    "VOL DN": "Vol-",
    "VOL UP": "Vol+",
    "OUT USB": "USB",
    "OUT BLE": "BLE",
    "BT CLR": "BtClr",
}


def svg_tag(name: str) -> str:
    return f"{{{SVG_NS}}}{name}"


def parse_dimension(raw: str) -> float:
    match = re.match(r"^([0-9]+(?:\.[0-9]+)?)", raw)
    if not match:
        raise ValueError(f"Unsupported SVG dimension: {raw}")
    return float(match.group(1))


def text_content(node: ET.Element) -> str:
    text = "".join(node.itertext())
    text = re.sub(r"\s+", " ", text).strip()
    return text


def abbreviate(text: str) -> str:
    if not text:
        return ""

    stripped = text.replace("…", "")
    if stripped.startswith("game_la") or stripped.startswith("game_layer"):
        return "game"
    if stripped.startswith("default_la") or stripped.startswith("default_layer"):
        return "default"
    for source, target in LAYER_NAME_MAP.items():
        if stripped.startswith(source):
            return target
    return TEXT_MAP.get(text, text)


def load_svg(path: Path) -> tuple[ET.Element, ET.Element, float, float]:
    root = ET.parse(path).getroot()
    style = root.find(svg_tag("style"))
    layer_group = root.find(svg_tag("g"))
    if style is None or layer_group is None:
        raise ValueError(f"Unexpected SVG structure in {path}")

    width = parse_dimension(root.attrib["width"])
    height = parse_dimension(root.attrib["height"])
    return root, style, width, height


def relabel(svg_root: ET.Element, label_text: str, label_id: str) -> None:
    layer_group = svg_root.find(svg_tag("g"))
    if layer_group is None:
        return

    label = layer_group.find(svg_tag("text"))
    if label is None:
        return

    label.text = label_text
    label.set("id", label_id)


def get_keys_container(layer_group: ET.Element) -> ET.Element:
    container = layer_group.find(svg_tag("g"))
    if container is None:
        raise ValueError("Missing key container")
    return container


def get_key_groups(layer_group: ET.Element) -> dict[str, ET.Element]:
    container = get_keys_container(layer_group)
    return {
        child.attrib.get("class", ""): child
        for child in container.findall(svg_tag("g"))
        if "keypos-" in child.attrib.get("class", "")
    }


def keypos_index(class_name: str) -> str:
    match = re.search(r"keypos-(\d+)", class_name)
    if not match:
        raise ValueError(f"Missing key position in class: {class_name}")
    return match.group(1)


def extract_legend_parts(key_group: ET.Element) -> dict[str, object]:
    cls = key_group.attrib.get("class", "")
    if " trans " in f" {cls} ":
        return {"tap": "", "hold": "", "shifted": "", "glyph": None}

    tap = ""
    hold = ""
    shifted = ""
    glyph = None
    for text_node in key_group.findall(svg_tag("text")):
        text_cls = text_node.attrib.get("class", "")
        content = abbreviate(text_content(text_node))
        if not content or content == "▽":
            continue
        if " tap" in f" {text_cls} ":
            tap = content
        elif " hold" in f" {text_cls} ":
            hold = content
        elif " shifted" in f" {text_cls} ":
            shifted = content

    use_node = key_group.find(svg_tag("use"))
    if use_node is not None:
        glyph_href = use_node.attrib.get("href") or use_node.attrib.get(f"{{{XLINK_NS}}}href") or ""
        glyph = {
            "id": glyph_href.removeprefix("#"),
        }

    return {"tap": tap, "hold": hold, "shifted": shifted, "glyph": glyph}


def extract_legend(key_group: ET.Element) -> str:
    parts = extract_legend_parts(key_group)
    if parts["hold"]:
        return f'{parts["tap"]} {parts["hold"]}'.strip()
    if parts["shifted"]:
        return f'{parts["tap"]} {parts["shifted"]}'.strip()
    return parts["tap"]


def build_legend_map(layer_group: ET.Element) -> dict[str, dict[str, object]]:
    legends: dict[str, dict[str, object]] = {}
    for class_name, key_group in get_key_groups(layer_group).items():
        legends[keypos_index(class_name)] = extract_legend_parts(key_group)
    return legends


def add_text(parent: ET.Element, x: float, y: float, cls: str, content: str) -> None:
    if not content:
        return
    text = ET.Element(svg_tag("text"), {"x": f"{x:g}", "y": f"{y:g}", "class": cls})
    text.text = content
    parent.append(text)


def add_glyph(
    parent: ET.Element,
    legend: dict[str, object],
    glyph_map: dict[str, ET.Element],
    x: float,
    y: float,
    cls: str,
) -> None:
    glyph_ref = legend.get("glyph")
    if glyph_ref is None:
        return
    glyph_id = str(glyph_ref.get("id", ""))
    glyph_template = glyph_map.get(glyph_id)
    if glyph_template is None:
        return
    glyph_group = ET.Element(
        svg_tag("g"),
        {
            "transform": f"translate({x:g}, {y:g}) scale(0.5)",
            "class": cls,
        },
    )
    glyph_group.append(copy.deepcopy(glyph_template))
    for node in glyph_group.iter():
        if node.tag == svg_tag("path"):
            if cls.startswith("overview-num"):
                node.set("fill", "#4a97a6")
            elif cls.startswith("overview-fun"):
                node.set("fill", "#ffc83d")
    parent.append(glyph_group)


def add_glyph_by_id(parent: ET.Element, glyph_map: dict[str, ET.Element], glyph_id: str, x: float, y: float, cls: str) -> None:
    glyph_template = glyph_map.get(glyph_id)
    if glyph_template is None:
        return
    glyph_group = ET.Element(
        svg_tag("g"),
        {
            "transform": f"translate({x:g}, {y:g}) scale(0.5)",
            "class": cls,
        },
    )
    glyph_group.append(copy.deepcopy(glyph_template))
    for node in glyph_group.iter():
        if node.tag == svg_tag("path"):
            if cls.startswith("overview-num"):
                node.set("fill", "#4a97a6")
            elif cls.startswith("overview-fun"):
                node.set("fill", "#ffc83d")
    parent.append(glyph_group)


def build_glyph_map(defs: ET.Element | None) -> dict[str, ET.Element]:
    glyph_map: dict[str, ET.Element] = {}
    if defs is None:
        return glyph_map

    for wrapper in defs.findall(svg_tag("svg")):
        glyph_id = wrapper.attrib.get("id")
        inner_svg = wrapper.find(svg_tag("svg"))
        if not glyph_id or inner_svg is None:
            continue
        icon_group = ET.Element(svg_tag("g"))
        for child in list(inner_svg):
            icon_child = copy.deepcopy(child)
            if icon_child.tag == svg_tag("path"):
                icon_child.set("class", "glyph-icon")
                if "stroke" in icon_child.attrib:
                    icon_child.attrib.pop("stroke")
            icon_group.append(icon_child)
        glyph_map[glyph_id] = icon_group
    return glyph_map


def build_overview(
    default_layer_group: ET.Element,
    num_legends: dict[str, dict[str, object]],
    fun_legends: dict[str, dict[str, object]],
    glyph_map: dict[str, ET.Element],
) -> ET.Element:
    overview_group = copy.deepcopy(default_layer_group)
    overview_group.set("class", "overview-section")

    label = overview_group.find(svg_tag("text"))
    if label is not None:
        overview_group.remove(label)

    keys_container = get_keys_container(overview_group)
    for key_group in keys_container.findall(svg_tag("g")):
        cls = key_group.attrib.get("class", "")
        if "keypos-" not in cls:
            continue

        key_index = keypos_index(cls)
        original_texts = key_group.findall(svg_tag("text"))
        default_parts = extract_legend_parts(key_group)
        default_tap = default_parts["tap"]
        default_hold = default_parts["hold"]
        default_shifted = default_parts["shifted"]
        default_legend = default_tap if default_tap else default_shifted
        for text_node in original_texts:
            key_group.remove(text_node)

        is_thumb = "rotate(" in key_group.attrib.get("transform", "")
        default_cls = "overview-default" + (" small" if len(default_legend) > 5 else "")
        if key_index == "34":
            default_cls = "overview-default thumb-layer thumb-layer-num"
            default_legend = "num&nav"
        elif key_index == "35":
            default_cls = "overview-default thumb-layer thumb-layer-fun"
            default_legend = "fun"

        add_text(
            key_group,
            0,
            2 if not is_thumb else 4,
            default_cls,
            default_legend,
        )
        secondary_default = default_hold if default_hold else default_shifted
        add_text(
            key_group,
            0,
            24 if not is_thumb else 33,
            "overview-default-hold",
            secondary_default,
        )
        num_legend = num_legends.get(key_index, {"tap": "", "glyph": None})
        fun_legend = fun_legends.get(key_index, {"tap": "", "glyph": None})

        add_text(key_group, -22, -21, "overview-num", str(num_legend.get("tap", "")))
        add_glyph(key_group, num_legend, glyph_map, -22, -24, "overview-num glyph")

        if fun_legend.get("tap") == "BT" and str(fun_legend.get("hold", "")).isdigit():
            add_glyph_by_id(key_group, glyph_map, "mdi:bluetooth", 4, -24, "overview-fun glyph")
            add_text(key_group, 22, -21, "overview-fun", str(int(str(fun_legend["hold"])) + 1))
        else:
            add_text(key_group, 22, -21, "overview-fun", str(fun_legend.get("tap", "")))
            add_glyph(key_group, fun_legend, glyph_map, 10, -24, "overview-fun glyph")

    return overview_group


def add_section_label(root: ET.Element, x: float, y: float, text: str) -> None:
    label = ET.Element(svg_tag("text"), {"x": f"{x:g}", "y": f"{y:g}", "class": "section-label"})
    label.text = text
    root.append(label)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--default-svg", required=True)
    parser.add_argument("--num-svg", required=True)
    parser.add_argument("--fun-svg", required=True)
    parser.add_argument("--game-svg", required=True)
    parser.add_argument("--combo-svg", required=True)
    parser.add_argument("--output-svg", required=True)
    args = parser.parse_args()

    default_root, default_style, width, overview_height = load_svg(Path(args.default_svg))
    num_root, _, _, _ = load_svg(Path(args.num_svg))
    fun_root, _, _, _ = load_svg(Path(args.fun_svg))
    game_root, _, _, game_height = load_svg(Path(args.game_svg))
    combo_root, _, _, combo_height = load_svg(Path(args.combo_svg))

    relabel(game_root, "game:", "game")
    relabel(combo_root, "combos:", "combos")

    default_layer_group = default_root.find(svg_tag("g"))
    num_layer_group = num_root.find(svg_tag("g"))
    fun_layer_group = fun_root.find(svg_tag("g"))
    game_layer_group = game_root.find(svg_tag("g"))
    combo_layer_group = combo_root.find(svg_tag("g"))
    if None in (default_layer_group, num_layer_group, fun_layer_group, game_layer_group, combo_layer_group):
        raise ValueError("Missing layer groups in generated SVGs")

    num_legends = build_legend_map(num_layer_group)
    fun_legends = build_legend_map(fun_layer_group)
    glyph_map = build_glyph_map(fun_root.find(svg_tag("defs")))
    overview_group = build_overview(default_layer_group, num_legends, fun_legends, glyph_map)

    section_gap = 56.0
    total_height = overview_height + combo_height + section_gap + game_height

    svg_root = ET.Element(
        svg_tag("svg"),
        {
            "width": f"{width:g}",
            "height": f"{total_height:g}",
            "viewBox": f"0 0 {width:g} {total_height:g}",
            "class": "keymap",
        },
    )

    style_el = copy.deepcopy(default_style)
    style_el.text = (style_el.text or "") + EXTRA_CSS
    svg_root.append(style_el)
    svg_root.append(overview_group)

    combo_wrapper = ET.Element(
        svg_tag("g"),
        {
            "transform": f"translate(0, {overview_height:g})",
            "class": "combo-section",
        },
    )
    combo_wrapper.append(copy.deepcopy(combo_layer_group))
    svg_root.append(combo_wrapper)

    game_wrapper = ET.Element(
        svg_tag("g"),
        {"transform": f"translate(0, {overview_height + combo_height + section_gap:g})", "class": "game-section"},
    )
    game_wrapper.append(copy.deepcopy(game_layer_group))
    svg_root.append(game_wrapper)

    Path(args.output_svg).write_text(
        ET.tostring(svg_root, encoding="unicode", xml_declaration=False),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
