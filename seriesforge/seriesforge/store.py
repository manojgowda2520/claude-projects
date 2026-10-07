"""Project file handling: locate, load, mutate and save seriesforge.json."""

import json
import os
import re
from datetime import date
from pathlib import Path

from seriesforge.errors import SeriesForgeError

PROJECT_FILE = "seriesforge.json"
SCHEMA = 1

_CODE_RE = re.compile(r"^s(?P<season>\d{1,3})e(?P<episode>\d{1,3})$", re.IGNORECASE)


def parse_code(code):
    """'s1e2', 'S01E02' -> (1, 2). Raises on anything else."""
    m = _CODE_RE.match(str(code).strip().replace(" ", ""))
    if not m:
        raise SeriesForgeError("episode code must look like S1E2, got %r" % code)
    return int(m.group("season")), int(m.group("episode"))


def format_code(season, episode):
    return "S%02dE%02d" % (int(season), int(episode))


def find_project(start=None):
    """Walk up from `start` looking for seriesforge.json. Returns Path or None."""
    env = os.environ.get("SERIESFORGE_PROJECT")
    if env:
        p = Path(env)
        p = p / PROJECT_FILE if p.is_dir() else p
        return p if p.is_file() else None
    here = Path(start or Path.cwd()).resolve()
    for folder in [here, *here.parents]:
        candidate = folder / PROJECT_FILE
        if candidate.is_file():
            return candidate
    return None


class Project:
    def __init__(self, path, data):
        self.path = Path(path)
        self.data = data

    # -- lifecycle ---------------------------------------------------
    @classmethod
    def create(cls, folder, title, genre="", format_minutes=30, logline=""):
        folder = Path(folder)
        path = folder / PROJECT_FILE
        if path.exists():
            raise SeriesForgeError("a project already exists at %s" % path)
        folder.mkdir(parents=True, exist_ok=True)
        data = {
            "schema": SCHEMA,
            "title": title,
            "genre": genre,
            "format_minutes": int(format_minutes),
            "logline": logline,
            "created": date.today().isoformat(),
            "characters": [],
            "locations": [],
            "threads": [],
            "seasons": [],
            "episodes": [],
        }
        project = cls(path, data)
        project.save()
        (folder / "drafts").mkdir(exist_ok=True)
        return project

    @classmethod
    def load(cls, start=None):
        path = find_project(start)
        if path is None:
            raise SeriesForgeError(
                "no %s found here or in any parent directory; run `sf init` first"
                % PROJECT_FILE
            )
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        if data.get("schema") != SCHEMA:
            raise SeriesForgeError(
                "project schema %r is not supported by this version" % data.get("schema")
            )
        return cls(path, data)

    def save(self):
        tmp = self.path.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(self.data, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        tmp.replace(self.path)

    @property
    def root(self):
        return self.path.parent

    @property
    def drafts_dir(self):
        d = self.root / "drafts"
        d.mkdir(exist_ok=True)
        return d

    # -- lookups -----------------------------------------------------
    def character(self, name, required=False):
        for c in self.data["characters"]:
            if c["name"].lower() == name.strip().lower():
                return c
        if required:
            raise SeriesForgeError("no character named %r in the bible" % name)
        return None

    def thread(self, ident, required=False):
        key = ident.strip().lower()
        for t in self.data["threads"]:
            if t["id"].lower() == key or t["name"].lower() == key:
                return t
        if required:
            raise SeriesForgeError("no thread %r" % ident)
        return None

    def season(self, number, required=False):
        for s in self.data["seasons"]:
            if s["number"] == int(number):
                return s
        if required:
            raise SeriesForgeError("season %s does not exist" % number)
        return None

    def episode(self, code, required=True):
        season, number = parse_code(code)
        for ep in self.data["episodes"]:
            if ep["season"] == season and ep["number"] == number:
                return ep
        if required:
            raise SeriesForgeError("no episode %s; add it with `sf episode add`"
                                   % format_code(season, number))
        return None

    def episodes_in(self, season=None):
        eps = self.data["episodes"]
        if season is not None:
            eps = [e for e in eps if e["season"] == int(season)]
        return sorted(eps, key=lambda e: (e["season"], e["number"]))

    def draft_path(self, episode):
        return self.root / episode["draft"]
