#!/usr/bin/env python3
"""
Interactive TUI for configuring guard rules.

Renders a grid where each rule has b/w/l/d columns.
Arrow keys navigate, space/enter toggles selection.
q or Ctrl+C exits and saves.

Usage: python3 guard_tui.py <guard-rules.json>
"""
from __future__ import annotations

import curses
import json
import sys
from pathlib import Path


LEVELS = ["block", "warn", "log", "disable"]
LEVEL_SHORT = {"block": "b", "warn": "w", "log": "l", "disable": "d"}
HEADER_LABELS = ["[b]lock", "[w]arn", "[l]og", "[d]isable"]


def load_rules(path: str) -> dict:
    p = Path(path)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"version": "1.0.0", "defaults": {"block_level": "block"}, "rules": []}


def save_rules(path: str, config: dict) -> None:
    Path(path).write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")


def run_tui(stdscr, config: dict) -> dict:
    curses.curs_set(0)
    curses.start_color()
    curses.use_default_colors()

    # Colors
    curses.init_pair(1, curses.COLOR_GREEN, -1)    # selected
    curses.init_pair(2, curses.COLOR_YELLOW, -1)    # warn
    curses.init_pair(3, curses.COLOR_CYAN, -1)      # header
    curses.init_pair(4, curses.COLOR_RED, -1)        # disable
    curses.init_pair(5, curses.COLOR_WHITE, -1)      # normal
    curses.init_pair(6, curses.COLOR_BLACK, curses.COLOR_WHITE)  # cursor row

    rules = config.get("rules", [])
    default_level = config.get("defaults", {}).get("block_level", "block")

    if not rules:
        return config

    # Build state: list of (rule_id, label, current_level)
    state = []
    for rule in rules:
        level = rule.get("block_level", default_level)
        if not rule.get("enabled", True):
            level = "disable"
        state.append({
            "id": rule["id"],
            "label": rule.get("label", rule["id"]),
            "level": level,
        })

    cursor_row = 0
    cursor_col = LEVELS.index(state[0]["level"]) if state else 0

    col_width = 8
    label_start = col_width * len(LEVELS) + 3

    while True:
        stdscr.clear()
        height, width = stdscr.getmaxyx()

        # Title
        title = "Guard Rules Configuration"
        subtitle = "Arrow keys: navigate | Space/Enter: select | s: save & exit | q: cancel"
        stdscr.addstr(0, 2, title, curses.A_BOLD | curses.color_pair(3))
        stdscr.addstr(1, 2, subtitle, curses.color_pair(5))
        stdscr.addstr(2, 2, f"Default level: {default_level}", curses.color_pair(5))

        # Header
        y_start = 4
        header_line = ""
        for i, label in enumerate(HEADER_LABELS):
            header_line += label.center(col_width)
        header_line += " | Rule"
        stdscr.addstr(y_start, 2, header_line, curses.A_BOLD | curses.color_pair(3))

        # Separator
        stdscr.addstr(y_start + 1, 2, "-" * min(width - 4, len(header_line) + 20), curses.color_pair(5))

        # Rules
        scroll_offset = 0
        visible_rows = height - y_start - 4
        if cursor_row >= scroll_offset + visible_rows:
            scroll_offset = cursor_row - visible_rows + 1
        if cursor_row < scroll_offset:
            scroll_offset = cursor_row

        for i in range(min(len(state), visible_rows)):
            row_idx = i + scroll_offset
            if row_idx >= len(state):
                break

            rule = state[row_idx]
            y = y_start + 2 + i
            is_cursor_row = row_idx == cursor_row

            # Draw level columns
            for col_idx, level in enumerate(LEVELS):
                is_selected = rule["level"] == level
                is_cursor = is_cursor_row and col_idx == cursor_col

                if is_selected:
                    marker = "[x]"
                else:
                    marker = "[ ]"

                # Choose color
                if is_cursor:
                    attr = curses.color_pair(6) | curses.A_BOLD
                elif is_selected and level == "block":
                    attr = curses.color_pair(1) | curses.A_BOLD
                elif is_selected and level == "warn":
                    attr = curses.color_pair(2) | curses.A_BOLD
                elif is_selected and level == "log":
                    attr = curses.color_pair(3) | curses.A_BOLD
                elif is_selected and level == "disable":
                    attr = curses.color_pair(4) | curses.A_BOLD
                else:
                    attr = curses.color_pair(5)

                cell = marker.center(col_width)
                try:
                    stdscr.addstr(y, 2 + col_idx * col_width, cell, attr)
                except curses.error:
                    pass

            # Draw separator and label
            sep = " | "
            label = rule["label"]
            if len(label) > width - label_start - 6:
                label = label[:width - label_start - 9] + "..."

            row_attr = curses.color_pair(6) if is_cursor_row else curses.color_pair(5)
            try:
                stdscr.addstr(y, 2 + len(LEVELS) * col_width, sep, row_attr)
                stdscr.addstr(y, 2 + len(LEVELS) * col_width + len(sep), label, row_attr)
            except curses.error:
                pass

        # Footer
        footer_y = min(height - 1, y_start + 2 + min(len(state), visible_rows) + 1)
        changes = sum(1 for s in state if s["level"] != default_level)
        footer = f"  {changes} rule(s) customized from default"
        try:
            stdscr.addstr(footer_y, 2, footer, curses.color_pair(5))
        except curses.error:
            pass

        stdscr.refresh()

        # Input
        key = stdscr.getch()

        if key == ord('q') or key == 27:  # q or ESC
            return None  # cancelled

        if key == ord('s'):  # save
            break

        if key == curses.KEY_UP:
            cursor_row = max(0, cursor_row - 1)
            cursor_col = LEVELS.index(state[cursor_row]["level"])

        elif key == curses.KEY_DOWN:
            cursor_row = min(len(state) - 1, cursor_row + 1)
            cursor_col = LEVELS.index(state[cursor_row]["level"])

        elif key == curses.KEY_LEFT:
            cursor_col = max(0, cursor_col - 1)

        elif key == curses.KEY_RIGHT:
            cursor_col = min(len(LEVELS) - 1, cursor_col + 1)

        elif key in (ord(' '), ord('\n'), curses.KEY_ENTER, 10, 13):
            state[cursor_row]["level"] = LEVELS[cursor_col]

    # Apply state back to config
    for rule_state in state:
        for rule in config["rules"]:
            if rule["id"] == rule_state["id"]:
                if rule_state["level"] == "disable":
                    rule["enabled"] = False
                    rule["block_level"] = default_level
                else:
                    rule["enabled"] = True
                    rule["block_level"] = rule_state["level"]

    return config


def main():
    if len(sys.argv) < 2:
        print("Usage: guard_tui.py <guard-rules.json>", file=sys.stderr)
        sys.exit(1)

    config_path = sys.argv[1]
    config = load_rules(config_path)

    if not config.get("rules"):
        print("No rules found in config.", file=sys.stderr)
        sys.exit(1)

    result = curses.wrapper(run_tui, config)

    if result is None:
        print("Cancelled.", file=sys.stderr)
        sys.exit(1)

    save_rules(config_path, result)

    # Print summary
    default_level = result.get("defaults", {}).get("block_level", "block")
    changes = 0
    for rule in result["rules"]:
        level = rule.get("block_level", default_level)
        enabled = rule.get("enabled", True)
        if not enabled:
            changes += 1
            print(f"  {rule['id']}: disabled")
        elif level != default_level:
            changes += 1
            print(f"  {rule['id']}: {level}")

    if changes == 0:
        print("  All rules at default level")
    else:
        print(f"  {changes} rule(s) customized")


if __name__ == "__main__":
    main()
