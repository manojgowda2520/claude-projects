"""Command line interface for SeriesForge."""

import argparse
import sys
from pathlib import Path

from seriesforge import __version__, fountain, report
from seriesforge.errors import SeriesForgeError
from seriesforge.store import Project, format_code, parse_code
from seriesforge.templates import STRUCTURES, get_structure


def _echo(lines):
    if isinstance(lines, str):
        lines = [lines]
    for line in lines:
        print(line)


def _split_names(value):
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


# ---------------------------------------------------------------- commands
def cmd_init(args):
    folder = Path(args.path or ".")
    project = Project.create(
        folder,
        title=args.title,
        genre=args.genre or "",
        format_minutes=args.minutes,
        logline=args.logline or "",
    )
    _echo([
        "Created %s" % project.path,
        "Next: sf character add \"NAME\" --role lead --want \"...\"",
        "      sf episode add S1E1 --title \"Pilot\" --logline \"...\"",
    ])


def cmd_character_add(args):
    project = Project.load()
    if project.character(args.name):
        raise SeriesForgeError("%s is already in the bible" % args.name)
    project.data["characters"].append({
        "name": args.name,
        "role": args.role or "",
        "want": args.want or "",
        "need": args.need or "",
        "flaw": args.flaw or "",
        "arc": args.arc or "",
        "voice": args.voice or "",
        "notes": args.notes or "",
    })
    project.save()
    _echo("Added %s to the bible." % args.name)


def cmd_character_list(args):
    project = Project.load()
    chars = project.data["characters"]
    if not chars:
        return _echo("No characters yet.")
    for c in chars:
        _echo("%-20s %-10s want: %s" % (c["name"], c["role"] or "-", c["want"] or "-"))
        for field in ("need", "flaw", "arc", "voice", "notes"):
            if c.get(field):
                _echo("    %-6s %s" % (field + ":", c[field]))


def cmd_location_add(args):
    project = Project.load()
    project.data["locations"].append({
        "name": args.name,
        "description": args.description or "",
    })
    project.save()
    _echo("Added location %s." % args.name)


def cmd_location_list(args):
    project = Project.load()
    if not project.data["locations"]:
        return _echo("No locations yet.")
    for loc in project.data["locations"]:
        _echo("%-24s %s" % (loc["name"], loc["description"]))


def cmd_thread_add(args):
    project = Project.load()
    if project.thread(args.id):
        raise SeriesForgeError("thread %r already exists" % args.id)
    project.data["threads"].append({
        "id": args.id,
        "name": args.name or args.id,
        "description": args.description or "",
        "status": "open",
        "introduced": args.introduced or "",
        "resolved": "",
    })
    project.save()
    _echo("Opened thread %s." % args.id)


def cmd_thread_list(args):
    project = Project.load()
    if not project.data["threads"]:
        return _echo("No threads yet.")
    for t in project.data["threads"]:
        _echo("%-12s %-8s %-28s %s"
              % (t["id"], t["status"], t["name"], t["description"]))


def cmd_thread_resolve(args):
    project = Project.load()
    thread = project.thread(args.id, required=True)
    thread["status"] = "resolved"
    thread["resolved"] = args.episode or ""
    project.save()
    _echo("Resolved thread %s%s"
          % (thread["id"], " in %s" % args.episode if args.episode else ""))


def cmd_season_add(args):
    project = Project.load()
    if project.season(args.number):
        raise SeriesForgeError("season %s already exists" % args.number)
    project.data["seasons"].append({
        "number": int(args.number),
        "title": args.title or "",
        "theme": args.theme or "",
        "arc": args.arc or "",
    })
    project.data["seasons"].sort(key=lambda s: s["number"])
    project.save()
    _echo("Added season %s." % args.number)


def cmd_episode_add(args):
    project = Project.load()
    season, number = parse_code(args.code)
    if project.episode(args.code, required=False):
        raise SeriesForgeError("%s already exists" % format_code(season, number))
    if not project.season(season):
        project.data["seasons"].append(
            {"number": season, "title": "", "theme": "", "arc": ""})
        project.data["seasons"].sort(key=lambda s: s["number"])
    code = format_code(season, number)
    episode = {
        "code": code,
        "season": season,
        "number": number,
        "title": args.title or "",
        "logline": args.logline or "",
        "summary": "",
        "structure": "",
        "beats": [],
        "scenes": [],
        "draft": "drafts/%s.fountain" % code,
    }
    project.data["episodes"].append(episode)
    project.data["episodes"].sort(key=lambda e: (e["season"], e["number"]))
    project.save()
    _echo("Added %s. Next: sf beats %s --structure five-act" % (code, code))


def cmd_episode_set(args):
    project = Project.load()
    episode = project.episode(args.code)
    for field in ("title", "logline", "summary"):
        value = getattr(args, field)
        if value is not None:
            episode[field] = value
    project.save()
    _echo("Updated %s." % episode["code"])


def cmd_beats(args):
    project = Project.load()
    episode = project.episode(args.code)
    if episode["beats"] and not args.force:
        raise SeriesForgeError(
            "%s already has a beat sheet; pass --force to replace it" % episode["code"])
    episode["beats"] = get_structure(args.structure)
    episode["structure"] = args.structure
    project.save()
    _echo(["%s beat sheet (%s):" % (episode["code"], args.structure)]
          + ["  [ ] %-18s %s" % (b["name"], b["prompt"]) for b in episode["beats"]])


def cmd_beat_note(args):
    project = Project.load()
    episode = project.episode(args.code)
    for beat in episode["beats"]:
        if beat["name"].lower() == args.beat.strip().lower():
            if args.note is not None:
                beat["note"] = args.note
            if args.done:
                beat["done"] = True
            if args.undone:
                beat["done"] = False
            project.save()
            return _echo("%s / %s updated." % (episode["code"], beat["name"]))
    raise SeriesForgeError(
        "%s has no beat named %r (have: %s)"
        % (episode["code"], args.beat, ", ".join(b["name"] for b in episode["beats"])))


def cmd_scene_add(args):
    project = Project.load()
    episode = project.episode(args.code)
    characters = _split_names(args.characters)
    for name in characters:
        if not project.character(name):
            _echo("note: %r is not in the bible yet (sf character add %r)"
                  % (name, name))
    scene = {
        "n": len(episode["scenes"]) + 1,
        "slug": args.slug,
        "summary": args.summary or "",
        "characters": characters,
        "thread": args.thread or "",
        "value_shift": args.value or "",
        "beat": args.beat or "",
    }
    if args.at is not None:
        index = max(0, min(len(episode["scenes"]), args.at - 1))
        episode["scenes"].insert(index, scene)
    else:
        episode["scenes"].append(scene)
    for i, sc in enumerate(episode["scenes"], start=1):
        sc["n"] = i
    project.save()
    _echo("%s scene %d: %s" % (episode["code"], scene["n"], scene["slug"]))


def cmd_scene_move(args):
    project = Project.load()
    episode = project.episode(args.code)
    scenes = episode["scenes"]
    if not 1 <= args.n <= len(scenes):
        raise SeriesForgeError("%s has no scene %d" % (episode["code"], args.n))
    scene = scenes.pop(args.n - 1)
    index = max(0, min(len(scenes), args.to - 1))
    scenes.insert(index, scene)
    for i, sc in enumerate(scenes, start=1):
        sc["n"] = i
    project.save()
    _echo("Moved %r to position %d." % (scene["slug"], scene["n"]))


def cmd_scene_remove(args):
    project = Project.load()
    episode = project.episode(args.code)
    scenes = episode["scenes"]
    if not 1 <= args.n <= len(scenes):
        raise SeriesForgeError("%s has no scene %d" % (episode["code"], args.n))
    scene = scenes.pop(args.n - 1)
    for i, sc in enumerate(scenes, start=1):
        sc["n"] = i
    project.save()
    _echo("Removed %r." % scene["slug"])


def cmd_draft(args):
    project = Project.load()
    episode = project.episode(args.code)
    path = project.draft_path(episode)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and not args.force:
        raise SeriesForgeError(
            "%s already exists; edit it, or pass --force to regenerate from the outline"
            % path)
    path.write_text(fountain.scaffold(project, episode), encoding="utf-8")
    _echo("Wrote %s" % path)


def cmd_export(args):
    project = Project.load()
    episode = project.episode(args.code)
    path = project.draft_path(episode)
    if args.format == "outline":
        text = "\n".join(report.outline(project, episode_code=args.code))
    else:
        if not path.is_file():
            raise SeriesForgeError("no draft for %s; run `sf draft %s` first"
                                   % (episode["code"], episode["code"]))
        source = path.read_text(encoding="utf-8")
        text = source if args.format == "fountain" else fountain.render_text(source)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        _echo("Wrote %s" % out)
    else:
        sys.stdout.write(text)


def cmd_outline(args):
    project = Project.load()
    _echo(report.outline(project, season=args.season, episode_code=args.code))


def cmd_status(args):
    project = Project.load()
    _echo(report.status(project))


def cmd_stats(args):
    project = Project.load()
    _echo(report.stats_lines(project, episode_code=args.code))


def cmd_continuity(args):
    project = Project.load()
    problems = report.continuity(project)
    if not problems:
        _echo("No continuity problems found.")
        return 0
    for severity, message in problems:
        _echo("%-5s %s" % (severity, message))
    errors = sum(1 for s, _ in problems if s == "error")
    _echo("")
    _echo("%d error(s), %d warning(s)" % (errors, len(problems) - errors))
    return 1 if errors else 0


def cmd_structures(args):
    for name, beats in sorted(STRUCTURES.items()):
        _echo("%s (%d beats)" % (name, len(beats)))
        for beat_name, prompt in beats:
            _echo("    %-18s %s" % (beat_name, prompt))
        _echo("")


# ---------------------------------------------------------------- parser
def build_parser():
    parser = argparse.ArgumentParser(
        prog="sf",
        description="SeriesForge - outline, track and draft an episodic series.",
    )
    parser.add_argument("--version", action="version", version="seriesforge " + __version__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="start a new series project here")
    p.add_argument("title")
    p.add_argument("--path", help="folder to create the project in (default: .)")
    p.add_argument("--genre")
    p.add_argument("--logline")
    p.add_argument("--minutes", type=int, default=30,
                   help="target episode length in minutes (default: 30)")
    p.set_defaults(func=cmd_init)

    # character
    p = sub.add_parser("character", help="series bible: characters")
    csub = p.add_subparsers(dest="action", required=True)
    q = csub.add_parser("add")
    q.add_argument("name")
    for field in ("role", "want", "need", "flaw", "arc", "voice", "notes"):
        q.add_argument("--" + field)
    q.set_defaults(func=cmd_character_add)
    csub.add_parser("list").set_defaults(func=cmd_character_list)

    # location
    p = sub.add_parser("location", help="series bible: standing sets")
    lsub = p.add_subparsers(dest="action", required=True)
    q = lsub.add_parser("add")
    q.add_argument("name")
    q.add_argument("--description")
    q.set_defaults(func=cmd_location_add)
    lsub.add_parser("list").set_defaults(func=cmd_location_list)

    # thread
    p = sub.add_parser("thread", help="serialised story threads")
    tsub = p.add_subparsers(dest="action", required=True)
    q = tsub.add_parser("add")
    q.add_argument("id", help="short handle, e.g. missing-brother")
    q.add_argument("--name")
    q.add_argument("--description")
    q.add_argument("--introduced", help="episode code where it starts")
    q.set_defaults(func=cmd_thread_add)
    tsub.add_parser("list").set_defaults(func=cmd_thread_list)
    q = tsub.add_parser("resolve")
    q.add_argument("id")
    q.add_argument("--episode")
    q.set_defaults(func=cmd_thread_resolve)

    # season
    p = sub.add_parser("season", help="seasons")
    ssub = p.add_subparsers(dest="action", required=True)
    q = ssub.add_parser("add")
    q.add_argument("number", type=int)
    q.add_argument("--title")
    q.add_argument("--theme")
    q.add_argument("--arc")
    q.set_defaults(func=cmd_season_add)

    # episode
    p = sub.add_parser("episode", help="episodes")
    esub = p.add_subparsers(dest="action", required=True)
    q = esub.add_parser("add")
    q.add_argument("code", help="e.g. S1E1")
    q.add_argument("--title")
    q.add_argument("--logline")
    q.set_defaults(func=cmd_episode_add)
    q = esub.add_parser("set")
    q.add_argument("code")
    q.add_argument("--title")
    q.add_argument("--logline")
    q.add_argument("--summary")
    q.set_defaults(func=cmd_episode_set)

    p = sub.add_parser("beats", help="lay a beat structure over an episode")
    p.add_argument("code")
    p.add_argument("--structure", default="five-act",
                   choices=sorted(STRUCTURES))
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_beats)

    p = sub.add_parser("beat", help="annotate a single beat")
    p.add_argument("code")
    p.add_argument("beat", help="beat name, e.g. Midpoint")
    p.add_argument("--note")
    p.add_argument("--done", action="store_true")
    p.add_argument("--undone", action="store_true")
    p.set_defaults(func=cmd_beat_note)

    p = sub.add_parser("scene", help="scene cards")
    scsub = p.add_subparsers(dest="action", required=True)
    q = scsub.add_parser("add")
    q.add_argument("code")
    q.add_argument("slug", help='e.g. "INT. NEWSROOM - NIGHT"')
    q.add_argument("--summary")
    q.add_argument("--characters", help="comma separated")
    q.add_argument("--thread")
    q.add_argument("--value", help="value shift, e.g. hope -> dread")
    q.add_argument("--beat", help="which beat this scene serves")
    q.add_argument("--at", type=int, help="insert at this position")
    q.set_defaults(func=cmd_scene_add)
    q = scsub.add_parser("move")
    q.add_argument("code")
    q.add_argument("n", type=int)
    q.add_argument("to", type=int)
    q.set_defaults(func=cmd_scene_move)
    q = scsub.add_parser("remove")
    q.add_argument("code")
    q.add_argument("n", type=int)
    q.set_defaults(func=cmd_scene_remove)

    p = sub.add_parser("draft", help="generate the .fountain draft from the outline")
    p.add_argument("code")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_draft)

    p = sub.add_parser("export", help="export a draft or outline")
    p.add_argument("code")
    p.add_argument("--format", default="text",
                   choices=["text", "fountain", "outline"])
    p.add_argument("--out", help="write to this file instead of stdout")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("outline", help="show the outline")
    p.add_argument("code", nargs="?")
    p.add_argument("--season", type=int)
    p.set_defaults(func=cmd_outline)

    sub.add_parser("status", help="series dashboard").set_defaults(func=cmd_status)

    p = sub.add_parser("stats", help="page count, dialogue share, who speaks most")
    p.add_argument("code", nargs="?")
    p.set_defaults(func=cmd_stats)

    sub.add_parser("continuity", help="check the bible against the outlines and drafts"
                   ).set_defaults(func=cmd_continuity)
    sub.add_parser("structures", help="list the available beat structures"
                   ).set_defaults(func=cmd_structures)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args) or 0
    except SeriesForgeError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
