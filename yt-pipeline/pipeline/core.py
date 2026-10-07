"""Shared plumbing: config loading, project paths, OpenAI client, cost tracking."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECTS = ROOT / "projects"


def load_env():
    """Read .env into os.environ without adding a dependency."""
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def load_config():
    return json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


def client():
    load_env()
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        die("OPENAI_API_KEY not found.\n"
            "  Fix: copy .env.example to .env and paste your key in,\n"
            "  or run:  $env:OPENAI_API_KEY = 'sk-...'")
    from openai import OpenAI
    return OpenAI(api_key=key)


def slugify(text, max_len=60):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:max_len].strip("-") or "untitled"


class Project:
    """One video. Every stage reads and writes inside this folder."""

    def __init__(self, slug):
        self.slug = slug
        self.dir = PROJECTS / slug
        self.audio = self.dir / "audio"
        self.images = self.dir / "images"
        self.render = self.dir / "render"
        for d in (self.dir, self.audio, self.images, self.render):
            d.mkdir(parents=True, exist_ok=True)

    @property
    def brief_path(self):
        return self.dir / "brief.json"

    @property
    def script_path(self):
        return self.dir / "script.json"

    @property
    def captions_path(self):
        return self.dir / "captions.srt"

    @property
    def voice_path(self):
        return self.audio / "voice.mp3"

    @property
    def final_path(self):
        return self.render / "final.mp4"

    def read_json(self, path):
        if not Path(path).exists():
            return None
        return json.loads(Path(path).read_text(encoding="utf-8"))

    def write_json(self, path, data):
        Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def script(self):
        data = self.read_json(self.script_path)
        if not data:
            die(f"No script yet for '{self.slug}'. Run the 'script' stage first.")
        return data

    # --- cost ledger -------------------------------------------------
    def log_cost(self, stage, usd, note=""):
        ledger = self.read_json(self.dir / "costs.json") or {"entries": [], "total_usd": 0.0}
        ledger["entries"].append({"stage": stage, "usd": round(usd, 4), "note": note})
        ledger["total_usd"] = round(sum(e["usd"] for e in ledger["entries"]), 4)
        self.write_json(self.dir / "costs.json", ledger)
        return ledger["total_usd"]


# --- console helpers -------------------------------------------------
def say(msg):
    print(f"  {msg}", flush=True)


def step(msg):
    print(f"\n\033[1m>> {msg}\033[0m", flush=True)


def warn(msg):
    print(f"  [!] {msg}", flush=True)


def die(msg):
    print(f"\n[X] {msg}\n", file=sys.stderr)
    sys.exit(1)


# --- ffmpeg ----------------------------------------------------------
def ffmpeg(args, cwd=None):
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args]
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        die(f"ffmpeg failed:\n{proc.stderr[-2000:]}")
    return proc


def audio_duration(path):
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True)
    if proc.returncode != 0:
        die(f"ffprobe failed on {path}:\n{proc.stderr[-500:]}")
    return float(proc.stdout.strip())
