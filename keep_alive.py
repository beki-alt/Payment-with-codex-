from __future__ import annotations

from threading import Thread

from flask import Flask

app = Flask(__name__)


@app.get("/")
def health():
    return {"status": "ok"}, 200


def run_keep_alive_server(port: int = 8080):
    thread = Thread(target=lambda: app.run(host="0.0.0.0", port=port), daemon=True)
    thread.start()
    return thread
