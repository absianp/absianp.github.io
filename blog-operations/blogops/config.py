import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def state_dir():
    path = Path(os.environ.get("BLOGOPS_STATE_DIR", str(Path.home()/".local/state/blog-operations"))).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path

def settings():
    data = json.loads((ROOT/"sites.json").read_text())
    override = state_dir()/"settings.json"
    if override.exists():
        local = json.loads(override.read_text())
        for key in ("limits", "providers"):
            data[key].update(local.get(key, {}))
        for site, values in local.get("sites", {}).items():
            if site not in data["sites"]:
                raise ValueError("Unknown site in settings")
            data["sites"][site].update(values)
    return data

def site_config(site):
    data = settings()
    if site not in data["sites"]:
        raise ValueError("Unknown site")
    config = dict(data["sites"][site], id=site)
    blog_root = Path(os.environ.get("BLOGOPS_BLOG_ROOT", str(ROOT.parent.parent))).resolve()
    config["root"] = str((blog_root/config["repo"]).resolve())
    config["pipeline"] = str(Path(config["root"])/"automation-pipeline")
    return config

def save_json(path, data):
    import tempfile
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(prefix=".json-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2, default=str)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
