#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

CONFIG="$ROOT_DIR/keymap_img/keymap_drawer.config.yaml"
KEYMAP="$ROOT_DIR/config/temper.keymap"
YAML_OUT="$ROOT_DIR/keymap_img/temper.yaml"
SVG_OUT="$ROOT_DIR/keymap_img/temper.svg"
DEFAULT_SVG="$TMP_DIR/default.svg"
NUM_SVG="$TMP_DIR/num_nav.svg"
FUN_SVG="$TMP_DIR/fun.svg"
GAME_SVG="$TMP_DIR/game.svg"
COMBO_SVG="$TMP_DIR/temper-combos.svg"

pushd "$ROOT_DIR" >/dev/null

keymap -c "$CONFIG" parse \
  -z "$KEYMAP" \
  -c 10 \
  -l default_layer num_nav_layer fun_layer game_layer \
  -o "$YAML_OUT"

# Normalize legends that keymap parse emits as plain text so draw can resolve them as glyphs.
perl -0pi -e 's/\bOUT USB\b/\$\$mdi:usb-port\$\$/g; s/\bOUT BLE\b/\$\$mdi:bluetooth\$\$/g; s/\bPG UP\b/\$\$mdi:pan-up\$\$/g; s/\bPG DN\b/\$\$mdi:pan-down\$\$/g; s/\bBT CLR\b/\$\$mdi:bluetooth-off\$\$/g; s/\bBTCLR\b/\$\$mdi:bluetooth-off\$\$/g' "$YAML_OUT"

keymap -c "$CONFIG" draw \
  "$YAML_OUT" \
  -k chocofi \
  -s default_layer \
  --keys-only \
  -o "$DEFAULT_SVG"

keymap -c "$CONFIG" draw \
  "$YAML_OUT" \
  -k chocofi \
  -s num_nav_layer \
  --keys-only \
  -o "$NUM_SVG"

keymap -c "$CONFIG" draw \
  "$YAML_OUT" \
  -k chocofi \
  -s fun_layer \
  --keys-only \
  -o "$FUN_SVG"

keymap -c "$CONFIG" draw \
  "$YAML_OUT" \
  -k chocofi \
  -s game_layer \
  --keys-only \
  -o "$GAME_SVG"

keymap -c "$CONFIG" draw \
  "$YAML_OUT" \
  -k chocofi \
  -s default_layer num_nav_layer fun_layer \
  --combos-only \
  -o "$COMBO_SVG"

python3 "$ROOT_DIR/scripts/merge_keymap_svgs.py" \
  --default-svg "$DEFAULT_SVG" \
  --num-svg "$NUM_SVG" \
  --fun-svg "$FUN_SVG" \
  --game-svg "$GAME_SVG" \
  --combo-svg "$COMBO_SVG" \
  --output-svg "$SVG_OUT"

popd >/dev/null
