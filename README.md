# power-logger

Live battery power monitor + CSV data logger for Linux laptops.

## Requirements

- Linux with `/sys/class/power_supply/BAT1`
- Python3

## Quick start

```sh
git clone https://github.com/aetherxt/power-logger.git && cd power-logger
make install
```

Add `~/.local/bin` to your PATH if not already:
```sh
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
exec bash
```

Run:
```sh
termpower          # live TUI monitor (press q to quit)
make record        # background CSV logging (Ctrl+C to stop)
make web           # web dashboard at http://localhost:8000
```

## Logging to CSV

Logs power data every 3 seconds to `~/power-log/YYYY-MM-DD.csv`:

```sh
python record.py                          # default: 3s interval, flush every 30s
python record.py --interval 3             # log every 3 seconds
python record.py --flush-interval 30      # write to disk every 30 seconds
python record.py -o ~/data                # custom output directory
```

### Auto-start on boot (systemd)

```sh
make service
systemctl --user daemon-reload
systemctl --user enable --now power-logger
journalctl --user -u power-logger -f      # watch logs
```

## CSV format

```
timestamp,energy_rate_w,percentage,state,charger_type
1719561600.123,12.5,64,charging,USB-C
```

`charger_type` is blank when discharging, or `USB-C`/`barrel`/`C [PD] PD_PPS` when charging.

## Makefile targets

| Target | Description |
|---|---|
| `make install` | Create venv, install deps, install `termpower` command |
| `make service` | Install systemd user service |
| `make run` | Run termpower via venv |
| `make record` | Run CSV logger via venv |
| `make web` | Run web dashboard on http://localhost:8000 |
| `make clean` | Remove venv, uninstall `termpower`, disable and remove systemd service |

## Web dashboard

A Flask web app at `web/app.py` visualises CSV data with Chart.js. Time-range selectors, zoom/pan, date picker, and colour-coded charging/discharging segments.

```sh
make web     # runs on http://localhost:8000
```

## Project structure

```
logger.py     — sysfs power sensor (importable)
termpower.py  — live TUI monitor (command: termpower)
record.py     — background CSV logger
web/app.py    — Flask web dashboard
Makefile      — install/run targets
```

## Storage

~600 KB per day (9h of 3s logging), ~18 MB/month, ~220 MB/year.
