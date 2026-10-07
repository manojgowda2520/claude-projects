#!/usr/bin/env python
"""Faceless YouTube video pipeline.

  python run.py new    "How black holes actually die" --niche "space science" --format short
  python run.py make   how-black-holes-actually-die
  python run.py batch  topics.txt --niche "space science"
  python run.py list
  python run.py doctor
"""
import argparse
import sys

from pipeline import assemble, captions, script, visuals, voice
from pipeline.core import (PROJECTS, Project, client, die, load_config, say, slugify,
                           step, warn)

STAGES = {"script": script.run, "voice": voice.run,
          "captions": captions.run, "visuals": visuals.run, "assemble": assemble.run}
ORDER = ["script", "voice", "captions", "visuals", "assemble"]


def cmd_new(args):
    slug = args.slug or slugify(args.topic)
    proj = Project(slug)
    proj.write_json(proj.brief_path, {
        "topic": args.topic, "niche": args.niche, "format": args.format,
        "seconds": args.seconds, "scenes": args.scenes,
    })
    say(f"created projects/{slug}/")
    say(f"next:  python run.py make {slug}")
    return slug


def cmd_make(args):
    proj = Project(args.slug)
    if not proj.brief_path.exists():
        die(f"No brief for '{args.slug}'. Create it with:  python run.py new \"<topic>\"")

    stages = args.only.split(",") if args.only else ORDER
    for name in stages:
        if name not in STAGES:
            die(f"Unknown stage '{name}'. Valid: {', '.join(ORDER)}")
        STAGES[name](args.slug, force=args.force)

    total = (proj.read_json(proj.dir / "costs.json") or {}).get("total_usd", 0)
    data = proj.read_json(proj.script_path) or {}
    print(f"\n{'=' * 62}")
    print(f"  {data.get('title', args.slug)}")
    print(f"  {proj.final_path}")
    print(f"  api cost: ${total:.3f}")
    print(f"{'=' * 62}\n")
    if data.get("thumbnail_idea"):
        say(f"thumbnail: {data['thumbnail_idea']}")


def cmd_batch(args):
    topics = [t.strip() for t in open(args.file, encoding="utf-8") if t.strip()
              and not t.startswith("#")]
    say(f"{len(topics)} topics queued")
    made, failed = [], []
    for i, topic in enumerate(topics, 1):
        step(f"[{i}/{len(topics)}] {topic}")
        slug = slugify(topic)
        try:
            cmd_new(argparse.Namespace(topic=topic, slug=slug, niche=args.niche,
                                       format=args.format, seconds=None, scenes=None))
            cmd_make(argparse.Namespace(slug=slug, only=None, force=False))
            made.append(slug)
        except SystemExit:
            raise
        except Exception as e:                       # noqa: BLE001 - keep the batch alive
            warn(f"{slug} failed: {type(e).__name__}: {e}")
            failed.append(slug)
    print(f"\n  done: {len(made)} built, {len(failed)} failed")
    for s in failed:
        print(f"    failed: {s}")


def cmd_list(_args):
    rows = sorted(p for p in PROJECTS.iterdir() if p.is_dir()) if PROJECTS.exists() else []
    if not rows:
        say("no projects yet")
        return
    for p in rows:
        proj = Project(p.name)
        data = proj.read_json(proj.script_path) or {}
        cost = (proj.read_json(proj.dir / "costs.json") or {}).get("total_usd", 0)
        mark = "[done]" if proj.final_path.exists() else "[wip] "
        print(f"  {mark} {p.name:<45} ${cost:>5.2f}  {data.get('title', '')}")


def cmd_doctor(_args):
    import shutil
    step("Environment")
    for tool in ("ffmpeg", "ffprobe"):
        path = shutil.which(tool)
        print(f"  {tool:<10} {path or 'MISSING - install ffmpeg and add it to PATH'}")
    cfg = load_config()
    step("Config")
    for k, v in cfg["models"].items():
        print(f"  {k:<12} {v}")
    print(f"  voice        {cfg['voice']}")
    step("API")
    try:
        available = {m.id for m in client().models.list()}
        print(f"  key works - {len(available)} models visible")
        for k, v in cfg["models"].items():
            ok = "ok" if v in available else "NOT AVAILABLE on this key"
            print(f"  {v:<20} {ok}")
    except SystemExit:
        pass          # client() already printed the fix
    except Exception as e:                           # noqa: BLE001
        print(f"  API check failed: {type(e).__name__}: {e}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("new", help="create a project brief")
    p.add_argument("topic")
    p.add_argument("--niche", default="general interest")
    p.add_argument("--format", choices=["short", "long"], default="short")
    p.add_argument("--slug")
    p.add_argument("--seconds", type=int)
    p.add_argument("--scenes", type=int)
    p.set_defaults(func=cmd_new)

    p = sub.add_parser("make", help="run the pipeline for a project")
    p.add_argument("slug")
    p.add_argument("--only", help="comma-separated stages: " + ",".join(ORDER))
    p.add_argument("--force", action="store_true", help="redo stages even if cached")
    p.set_defaults(func=cmd_make)

    p = sub.add_parser("batch", help="build one video per line of a topics file")
    p.add_argument("file")
    p.add_argument("--niche", default="general interest")
    p.add_argument("--format", choices=["short", "long"], default="short")
    p.set_defaults(func=cmd_batch)

    sub.add_parser("list", help="show all projects").set_defaults(func=cmd_list)
    sub.add_parser("doctor", help="check tools, key and model access").set_defaults(func=cmd_doctor)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n  interrupted - progress is cached, rerun to resume")
        sys.exit(130)
