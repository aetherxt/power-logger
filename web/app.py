import csv
import os
from datetime import datetime

from flask import Flask, jsonify, render_template, request

app = Flask(__name__)
LOG_DIR = os.path.expanduser("~/power-log")

def get_all_csv():
    if not os.path.isdir(LOG_DIR):
        return []
    files = sorted(f for f in os.listdir(LOG_DIR) if f.endswith(".csv"))
    return files

def get_latest_csv():
    files = get_all_csv()
    return files[-1] if files else None

def parse_csv(filename):
    path = os.path.join(LOG_DIR, filename)
    rows = []
    with open(path) as f:
        for row in csv.DictReader(f):
            try:
                ts = float(row["timestamp"])
                row["timestamp"] = ts
                row["time"] = datetime.fromtimestamp(ts).isoformat()
                row["energy_rate_w"] = float(row["energy_rate_w"])
                row["percentage"] = float(row["percentage"])
            except (ValueError, KeyError):
                continue
            rows.append(row)
    return rows

@app.route("/")
def index():
    return render_template("index.html", latest_file=get_latest_csv(), csv_files=get_all_csv())

@app.route("/api/data")
def api_data():
    file = request.args.get("file") or get_latest_csv()
    if not file:
        return jsonify({"error": "No CSV files found"}), 404
    return jsonify(parse_csv(file))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
