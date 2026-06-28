#!/usr/bin/env python
import os
import sys
import time
import shutil
import select
import tty
import termios
import re
import glob
import subprocess
import psutil
from logger import get_power_info


H = 11
INTERVAL = 1.0
LEFT_W = 9
MIN_COLS = 85
MIN_ROWS = 30
_ANSI_RE = re.compile(r'\033\[[0-9;]*[a-zA-Z]')


def _vlen(s):
    return len(_ANSI_RE.sub('', s))


def _compact(values, width):
    n = len(values)
    if n <= width:
        return list(values)
    out = []
    bucket = n / width
    for i in range(width):
        start = int(i * bucket)
        end = int((i + 1) * bucket)
        chunk = values[start:end]
        out.append(sum(chunk) / len(chunk))
    return out


def _compact_states(values, width):
    n = len(values)
    if n <= width:
        return list(values)
    out = []
    bucket = n / width
    for i in range(width):
        start = int(i * bucket)
        end = int((i + 1) * bucket)
        chunk = values[start:end]
        out.append(max(set(chunk), key=chunk.count))
    return out


def _color_rows(rows, compacted_states, left_w):
    for ri, row in enumerate(rows):
        left_part = row[:left_w]
        braille = row[left_w:]
        colored = []
        for ci, ch in enumerate(braille):
            idx0 = ci * 2
            idx1 = ci * 2 + 1
            if idx0 < len(compacted_states):
                s = compacted_states[idx1] if idx1 < len(compacted_states) else compacted_states[idx0]
                if s == "charging" or s == "fully-charged":
                    colored.append(f"{_GREEN}{ch}{_RESET}")
                else:
                    colored.append(f"{_RED}{ch}{_RESET}")
            else:
                colored.append(ch)
        rows[ri] = left_part + ''.join(colored)
    return rows


def braille_grid(values, lo, hi, cols):
    pixel_rows = H * 4
    grid = [[0x2800 for _ in range(cols)] for _ in range(H)]

    if not values:
        return [''.join(chr(c) for c in row) for row in grid]

    for idx, v in enumerate(values):
        if hi > lo:
            p = round((v - lo) / (hi - lo) * (pixel_rows - 1))
            p = max(0, min(pixel_rows - 1, p))
        else:
            p = pixel_rows // 2

        braille_row = (H - 1) - (p // 4)
        bit_in_row = p % 4

        braille_col = idx // 2
        if braille_col >= cols:
            break
        is_left = (idx % 2 == 0)

        bit = [6, 2, 1, 0][bit_in_row] if is_left else [7, 5, 4, 3][bit_in_row]
        grid[braille_row][braille_col] |= (1 << bit)

    return [''.join(chr(c) for c in row) for row in grid]


def format_graph(lines, lo, hi, left_w, fmt, unit, label_step=1):
    rows = []
    for i, line in enumerate(lines):
        if i % label_step == 0:
            frac = (H - 1 - i) / (H - 1)
            val = lo + (hi - lo) * frac
            label = f"{fmt.format(val)}{unit}"
            if i == 0:
                left = label.rjust(left_w - 2) + " ┐"
            elif i == H - 1:
                left = label.rjust(left_w - 2) + " ┘"
            else:
                left = label.rjust(left_w - 2) + " ┤"
        else:
            left = " ┤".rjust(left_w)
        rows.append(left + line)
    return rows


def get_cpu_usage():
    try:
        return round(psutil.cpu_percent(interval=None))
    except Exception:
        return 0


def get_gpu_info():
    igpu = None
    egpu = None

    for path in glob.glob('/sys/class/drm/card*/device/gpu_busy_percent'):
        try:
            with open(path) as f:
                val = int(f.read().strip())
            card_dir = os.path.dirname(os.path.dirname(path))
            has_edp = bool(glob.glob(os.path.join(card_dir, '*eDP*')))
            if has_edp:
                igpu = val
            else:
                egpu = val
        except Exception:
            continue

    if egpu is None:
        try:
            r = subprocess.run(
                ['nvidia-smi', '--query-gpu=utilization.gpu', '--format=csv,noheader,nounits'],
                capture_output=True, text=True, timeout=2
            )
            if r.returncode == 0 and r.stdout.strip():
                egpu = int(float(r.stdout.strip()))
        except Exception:
            pass

    if igpu is None:
        igpu = 0
    return igpu, egpu


def battery_bar(pct, width=6):
    C0 = (40, 85, 50)
    C1 = (150, 255, 160)
    TRACK = (53, 58, 63)

    def fg(r, g, b):
        return f'\033[38;2;{r};{g};{b}m'

    filled = round(pct / 100 * width)
    cells = []
    for i in range(width):
        if i < filled:
            t = i / max(width - 1, 1)
            r = round(C0[0] + (C1[0] - C0[0]) * t)
            g = round(C0[1] + (C1[1] - C0[1]) * t)
            b = round(C0[2] + (C1[2] - C0[2]) * t)
            cells.append(fg(r, g, b) + '\u25a0')
        else:
            cells.append(fg(*TRACK) + '\u25a0')
    return ''.join(cells)


_WHITE = '\033[38;2;200;200;200m'
_GREEN = '\033[38;2;166;218;149m'
_RED = '\033[38;2;237;135;150m'
_PANEL_BG = '\033[48;2;36;39;58m'
_RESET = '\033[0m'


def pill(text):
    return f'{_PANEL_BG} {text} '


def build_display(watts, bats, states, info, graph_w):
    ts, rate, pct, state, charger = info
    charger_str = f"  CHARGER: {charger}" if charger else ""

    target = graph_w * 2
    cw = _compact(watts, target)
    cb = _compact(bats, target)
    cs = _compact_states(states, target)

    if not hasattr(build_display, '_w_lo'):
        build_display._w_lo = max(0.0, rate - 5.0)
        build_display._w_hi = rate + 5.0

    lo_w, hi_w = build_display._w_lo, build_display._w_hi

    if cw:
        dmin, dmax = min(cw), max(cw)
        rang = hi_w - lo_w
        changed = False
        if dmax >= hi_w - rang * 0.1:
            hi_w = dmax + rang * 0.2
            rang = hi_w - lo_w
            changed = True
        if dmin <= lo_w + rang * 0.1:
            lo_w = max(0.0, dmin - rang * 0.2)
            changed = True
        if changed:
            build_display._w_lo = lo_w
            build_display._w_hi = hi_w

    if not hasattr(build_display, '_b_lo'):
        init = round(pct / 5.0) * 5.0
        build_display._b_lo = max(0.0, init - 5.0)
        build_display._b_hi = min(100.0, init + 5.0)

    b_lo, b_hi = build_display._b_lo, build_display._b_hi

    if cb:
        changed = False
        if pct <= b_lo + 3:
            b_lo = max(0.0, b_lo - 5.0)
            changed = True
        if pct >= b_hi - 3:
            b_hi = min(100.0, b_hi + 5.0)
            changed = True
        if changed:
            build_display._b_lo = b_lo
            build_display._b_hi = b_hi

    cpu = get_cpu_usage()
    igpu, egpu = get_gpu_info()
    gpu_str = f"iGPU: {igpu}%"
    if egpu is not None:
        gpu_str += f"  eGPU: {egpu}%"
    p_power = pill(f"POWER: {rate:.2f}W")
    state_color = _GREEN if state == "charging" or state == "fully-charged" else _RED
    p_bat = pill(f"{state_color}BAT: {pct:.0f}%{_RESET}{_PANEL_BG}  {battery_bar(pct)}")
    p_cpu = pill(f"{_WHITE}CPU: {cpu}%")
    p_gpu = pill(f"{_WHITE}{gpu_str}")
    p_state = pill(f"{state_color}{state}{charger_str}{_RESET}{_PANEL_BG}")
    header = f"{p_power}  {p_bat}  {p_cpu}  {p_gpu}  {p_state}"

    w_lines = braille_grid(cw, lo_w, hi_w, graph_w)
    b_lines = braille_grid(cb, b_lo, b_hi, graph_w)

    graph_inner = LEFT_W + graph_w
    inner = max(graph_inner, _vlen(header) + 4)

    w_rows = format_graph(w_lines, lo_w, hi_w, LEFT_W, "{:.0f}", "W", label_step=2)
    b_rows = format_graph(b_lines, b_lo, b_hi, LEFT_W, "{:.0f}", "%", label_step=2)
    w_rows = _color_rows(w_rows, cs, LEFT_W)
    b_rows = _color_rows(b_rows, cs, LEFT_W)

    w_info = f"WATTAGE: {rate:.2f}W  |  RANGE: [{lo_w:.0f}-{hi_w:.0f}W]  |  MIN: {min(watts):.1f}  |  MAX: {max(watts):.1f}"
    b_info = f"BATTERY: {pct:.0f}%  |  RANGE: [{b_lo:.0f}-{b_hi:.0f}%]  |  MIN: {min(bats):.0f}  |  MAX: {max(bats):.0f}"

    # ── wattage pill ──
    n = _vlen(w_info)
    rem = inner - n - 4
    w_top = f"{_WHITE}╭─ {_PANEL_BG}{w_info} {_WHITE}─{'─' * rem}╮"
    w_lines_pill = [w_top]
    for r in w_rows:
        pad = inner - _vlen(r)
        w_lines_pill.append(f"{_WHITE}│{_PANEL_BG}{r}{' ' * pad}{_WHITE}│")
    w_lines_pill.append(f"{_WHITE}╰{'─' * inner}╯")

    # ── header pill ──
    hdr_pad = inner - 1 - _vlen(header)
    h_top = f"{_WHITE}╭{'─' * inner}╮"
    h_row = f"{_WHITE}│{_PANEL_BG} {header}{' ' * hdr_pad}{_WHITE}│"
    h_bot = f"{_WHITE}╰{'─' * inner}╯"

    # ── battery pill ──
    n = _vlen(b_info)
    rem = inner - n - 4
    b_top = f"{_WHITE}╭─ {_PANEL_BG}{b_info} {_WHITE}─{'─' * rem}╮"
    b_lines_pill = [b_top]
    for r in b_rows:
        pad = inner - _vlen(r)
        b_lines_pill.append(f"{_WHITE}│{_PANEL_BG}{r}{' ' * pad}{_WHITE}│")
    b_lines_pill.append(f"{_WHITE}╰{'─' * inner}╯")

    return '\n\n'.join(['\n'.join([h_top, h_row, h_bot]), '\n'.join(w_lines_pill), '\n'.join(b_lines_pill)])


def main():
    watts = []
    bats = []
    states = []

    try:
        from rich.live import Live
        from rich.text import Text
    except ImportError:
        print("rich is required: pip install rich")
        sys.exit(1)

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        new = termios.tcgetattr(fd)
        new[1] |= termios.OPOST | termios.ONLCR
        termios.tcsetattr(fd, termios.TCSADRAIN, new)
        with Live(screen=True, refresh_per_second=1) as live:
            while True:
                term = shutil.get_terminal_size()
                graph_w = term.columns - LEFT_W - 2

                info = get_power_info()
                watts.append(info[1])
                bats.append(info[2])
                states.append(info[3])

                if term.columns < MIN_COLS or term.lines < MIN_ROWS:
                    msg = f"Terminal too small — need {MIN_COLS}x{MIN_ROWS}, currently {term.columns}x{term.lines}"
                    pad = max(0, (term.columns - len(msg)) // 2)
                    display = f"\n\n{' ' * pad}{msg}"
                else:
                    display = build_display(watts, bats, states, info, graph_w)

                display = display.replace('\033[0m', f'\033[0m{_PANEL_BG}')
                lines = display.split('\n')
                for i, line in enumerate(lines):
                    v = _vlen(line)
                    n = max(0, term.columns - v)
                    lines[i] = f'{_PANEL_BG}{line}{" " * n}\033[0m'
                for _ in range(max(0, term.lines - len(lines))):
                    lines.append(f'{_PANEL_BG}{" " * term.columns}\033[0m')
                display = '\n'.join(lines)

                live.update(Text.from_ansi(display))

                if select.select([fd], [], [], 0) == ([fd], [], []):
                    c = os.read(fd, 1).decode()
                    if c == 'q' or c == '\x03':
                        break
                time.sleep(INTERVAL)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


if __name__ == "__main__":
    main()
