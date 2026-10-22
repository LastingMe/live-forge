import copy
import json

SETTINGS_FILE = "settings.json"

DEFAULTS = {
    # general
    "default_mode": "ONLINE",
    "default_source": "TEST",
    "start_live": True,
    "default_speed": "100%",
    "nudge_seconds": 0.5,
    "auto_select_new": True,
    "start_paused": True,
    "mark_durations": [1.0, 5.0, 7.0, 10.0, 15.0],
    # capture
    "buffer_width": 1280,
    "buffer_height": 720,
    "buffer_crf": 23,
    "buffer_seconds": 30,
    "master_seconds": 20,
    # feeds
    "online_feeds": ["OBS_1", "OBS_2", "OBS_3"],
    "lan_feeds": [f"Player_{i}" for i in range(1, 11)],
    "base_port": 9001,
    # output
    "program_file": "",
    "program_height": 720,
    "program_fps": 60,
    # remote and storage
    "remote_enabled": True,
    "remote_port": 8765,
    "events_dir": "events",
    "buffer_dir": "buffer",
}


def load() -> dict:
    cfg = copy.deepcopy(DEFAULTS)
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        for k, v in data.items():
            if k in cfg and type(v) is type(cfg[k]):
                cfg[k] = v
    except Exception:
        pass
    return cfg


def save(cfg: dict):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)