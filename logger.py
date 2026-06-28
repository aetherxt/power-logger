import os
import re
import time

BAT = "/sys/class/power_supply/BAT1"


def _read_sysfs(path):
    with open(f"{BAT}/{path}") as f:
        return f.read().strip()


def get_power_info():
    current_ua = int(_read_sysfs("current_now"))
    voltage_uv = int(_read_sysfs("voltage_now"))
    energy_rate = current_ua * voltage_uv * 1e-12

    percentage = float(_read_sysfs("capacity"))
    state = _read_sysfs("status").lower()

    charger_type = getattr(get_power_info, '_cached_charger', None)
    if state == "charging":
        if getattr(get_power_info, '_last_state', None) != "charging":
            charger_type = None
            for entry in sorted(os.listdir("/sys/class/power_supply")):
                if not entry.startswith("ucsi"):
                    continue
                data = open(f"/sys/class/power_supply/{entry}/uevent").read()
                if re.search(r"ONLINE=1", data):
                    usb = re.search(r"POWER_SUPPLY_USB_TYPE=(.+)", data)
                    charger_type = usb.group(1) if usb else "USB"
                    break

            if charger_type is None:
                for entry in sorted(os.listdir("/sys/class/power_supply")):
                    if entry.startswith("ucsi") or entry.startswith("BAT"):
                        continue
                    data = open(f"/sys/class/power_supply/{entry}/uevent").read()
                    if re.search(r"ONLINE=1", data):
                        charger_type = "barrel"
                        break

            get_power_info._cached_charger = charger_type
    else:
        get_power_info._cached_charger = None

    get_power_info._last_state = state
    return [time.time(), energy_rate, percentage, state, charger_type]


if __name__ == "__main__":
    print(get_power_info())
