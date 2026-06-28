import os
import sys
import time
import shutil
import select
import tty
import termios

sys.path.insert(0, os.path.dirname(__file__))
import termpower

# ── New battery scale logic (round 5, init ±5, expand by 5 at boundary) ──
_orig_build = termpower.build_display

def _build_with_new_battery_scale(watts, bats, states, info, graph_w):
    ts, rate, pct, state, charger = info
    charger_str = f"  CHARGER: {charger}" if charger else ""

    target = graph_w * 2
    cw = termpower._compact(watts, target)
    cb = termpower._compact(bats, target)
    cs = termpower._compact_states(states, target)

    # ── Wattage scale (unchanged) ──
    if not hasattr(_build_with_new_battery_scale, '_w_lo'):
        _build_with_new_battery_scale._w_lo = max(0.0, rate - 5.0)
        _build_with_new_battery_scale._w_hi = rate + 5.0

    lo_w, hi_w = _build_with_new_battery_scale._w_lo, _build_with_new_battery_scale._w_hi

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
            _build_with_new_battery_scale._w_lo = lo_w
            _build_with_new_battery_scale._w_hi = hi_w

    # ── Battery scale (NEW: round 5, ±5, expand by 5 at boundary) ──
    if not hasattr(_build_with_new_battery_scale, '_b_lo'):
        init = round(pct / 5.0) * 5.0
        _build_with_new_battery_scale._b_lo = max(0.0, init - 5.0)
        _build_with_new_battery_scale._b_hi = min(100.0, init + 5.0)

    b_lo, b_hi = _build_with_new_battery_scale._b_lo, _build_with_new_battery_scale._b_hi

    if cb:
        changed = False
        if pct <= b_lo + 3:
            b_lo = max(0.0, b_lo - 5.0)
            changed = True
        if pct >= b_hi - 3:
            b_hi = min(100.0, b_hi + 5.0)
            changed = True
        if changed:
            _build_with_new_battery_scale._b_lo = b_lo
            _build_with_new_battery_scale._b_hi = b_hi

    # ── Header ──
    p_power = termpower.pill(f"POWER: {rate:.2f}W")
    state_color = termpower._GREEN if state == "charging" or state == "fully-charged" else termpower._RED
    p_bat = termpower.pill(f"{state_color}BAT: {pct:.0f}%{termpower._RESET}{termpower._PANEL_BG}  {termpower.battery_bar(pct)}")
    p_cpu = termpower.pill(f"{termpower._WHITE}CPU: 23%")
    p_gpu = termpower.pill(f"{termpower._WHITE}iGPU: 45%")
    p_state = termpower.pill(f"{state_color}{state}{charger_str}{termpower._RESET}{termpower._PANEL_BG}")
    header = f"{p_power}  {p_bat}  {p_cpu}  {p_gpu}  {p_state}"

    # ── Render ──
    w_lines = termpower.braille_grid(cw, lo_w, hi_w, graph_w)
    b_lines = termpower.braille_grid(cb, b_lo, b_hi, graph_w)

    left_w = termpower.LEFT_W
    graph_inner = left_w + graph_w
    inner = max(graph_inner, termpower._vlen(header) + 4)

    w_rows = termpower.format_graph(w_lines, lo_w, hi_w, left_w, "{:.0f}", "W", label_step=2)
    b_rows = termpower.format_graph(b_lines, b_lo, b_hi, left_w, "{:.0f}", "%", label_step=2)
    w_rows = termpower._color_rows(w_rows, cs, left_w)
    b_rows = termpower._color_rows(b_rows, cs, left_w)

    w_info = f"WATTAGE: {rate:.2f}W  |  RANGE: [{lo_w:.0f}-{hi_w:.0f}W]  |  MIN: {min(watts):.1f}  |  MAX: {max(watts):.1f}"
    b_info = f"BATTERY: {pct:.0f}%  |  RANGE: [{b_lo:.0f}-{b_hi:.0f}%]  |  MIN: {min(bats):.0f}  |  MAX: {max(bats):.0f}"

    top = f"╭{'─' * inner}╮"
    hdr_pad = inner - 1 - termpower._vlen(header)
    hdr = f"│ {header}{' ' * hdr_pad}│"
    sep = f"├{'─' * inner}┤"
    bot = f"╰{'─' * inner}╯"

    lines = [top, hdr, sep]
    for r in w_rows:
        lines.append(f"│{r}│")
    lines.append(f"│{' ' * left_w}{w_info.ljust(inner - left_w)}│")
    lines.append(sep)
    for r in b_rows:
        lines.append(f"│{r}│")
    lines.append(f"│{' ' * left_w}{b_info.ljust(inner - left_w)}│")
    lines.append(bot)

    return '\n'.join(lines)


# ── Live test ──
for attr in ['_b_lo', '_b_hi', '_w_lo', '_w_hi']:
    if hasattr(_build_with_new_battery_scale, attr):
        delattr(_build_with_new_battery_scale, attr)
if hasattr(termpower.build_display, '_b_lo'):
    del termpower.build_display._b_lo
if hasattr(termpower.build_display, '_w_lo'):
    del termpower.build_display._w_lo

battery_readings = list(range(74, 19, -1)) + list(range(21, 81))
wattage_readings = [round(15.2 - i * 0.2, 1) for i in range(55)] + [round(-24.0 + i * 1.0, 1) for i in range(25)] + [0.0] * 35
states_seq = ["discharging"] * 55 + ["charging"] * 60

fd = sys.stdin.fileno()
old = termios.tcgetattr(fd)
try:
    tty.setraw(fd)
    new = termios.tcgetattr(fd)
    new[1] |= termios.OPOST | termios.ONLCR
    termios.tcsetattr(fd, termios.TCSADRAIN, new)

    from rich.live import Live
    from rich.text import Text

    with Live(screen=True, refresh_per_second=2) as live:
        watts_hist = []
        bats_hist = []
        states_hist = []
        for i in range(len(battery_readings)):
            pct, watt = battery_readings[i], wattage_readings[i]
            state = states_seq[i]
            watts_hist.append(watt)
            bats_hist.append(float(pct))
            states_hist.append(state)
            term = shutil.get_terminal_size()
            graph_w = max(10, term.columns - 11)
            info = [time.time(), watt, float(pct), state, "USB-C"]
            display = _build_with_new_battery_scale(watts_hist, bats_hist, states_hist, info, graph_w)

            display = display.replace('\033[0m', f'\033[0m{termpower._PANEL_BG}')
            lines = display.split('\n')
            for i, line in enumerate(lines):
                v = termpower._vlen(line)
                n = max(0, term.columns - v)
                lines[i] = f'{termpower._PANEL_BG}{line}{" " * n}\033[0m'
            for _ in range(max(0, term.lines - len(lines))):
                lines.append(f'{termpower._PANEL_BG}{" " * term.columns}\033[0m')
            display = '\n'.join(lines)

            live.update(Text.from_ansi(display))
            time.sleep(0.5)

            if select.select([fd], [], [], 0) == ([fd], [], []):
                c = os.read(fd, 1).decode()
                if c == 'q' or c == '\x03':
                    break
finally:
    termios.tcsetattr(fd, termios.TCSADRAIN, old)
