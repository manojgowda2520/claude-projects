"""Read-only views over a project: outlines, status, continuity, stats."""

from seriesforge import fountain


def _bar(done, total, width=18):
    filled = 0 if not total else int(round(width * done / total))
    return "[" + "#" * filled + "." * (width - filled) + "]"


def episode_progress(project, episode):
    """Return (beats_done, beats_total, draft_stats or None)."""
    beats = episode.get("beats") or []
    done = sum(1 for b in beats if b.get("done"))
    path = project.draft_path(episode)
    stats = None
    if path.is_file():
        stats = fountain.stats(path.read_text(encoding="utf-8"))
    return done, len(beats), stats


def status(project):
    d = project.data
    lines = [
        "%s%s" % (d["title"], " (%s)" % d["genre"] if d["genre"] else ""),
        "  %s" % (d["logline"] or "no logline yet"),
        "  %d min format | %d characters | %d threads | %d episodes"
        % (d["format_minutes"], len(d["characters"]), len(d["threads"]),
           len(d["episodes"])),
        "",
    ]
    if not d["episodes"]:
        lines.append("No episodes yet. Try: sf episode add S1E1 --title \"Pilot\"")
        return lines

    for season in sorted({e["season"] for e in d["episodes"]}):
        meta = project.season(season)
        header = "Season %d" % season
        if meta and meta.get("title"):
            header += " - %s" % meta["title"]
        lines.append(header)
        for ep in project.episodes_in(season):
            done, total, stats = episode_progress(project, ep)
            pages = "%4.1fp" % stats["pages"] if stats else "  --p"
            lines.append(
                "  %-7s %-28s %s %2d/%-2d beats  %s  %d scenes"
                % (ep["code"], (ep.get("title") or "-")[:28], _bar(done, total),
                   done, total, pages, len(ep.get("scenes") or []))
            )
        lines.append("")
    return lines


def outline(project, season=None, episode_code=None):
    lines = []
    episodes = ([project.episode(episode_code)] if episode_code
                else project.episodes_in(season))
    for ep in episodes:
        lines.append("%s  %s" % (ep["code"], ep.get("title") or "(untitled)"))
        if ep.get("logline"):
            lines.append("  logline: %s" % ep["logline"])
        if ep.get("structure"):
            lines.append("  structure: %s" % ep["structure"])
        for beat in ep.get("beats") or []:
            mark = "x" if beat.get("done") else " "
            lines.append("  [%s] %-18s %s" % (mark, beat["name"],
                                              beat.get("note") or beat["prompt"]))
        for scene in ep.get("scenes") or []:
            who = ", ".join(scene.get("characters") or []) or "-"
            lines.append("   %2d. %s" % (scene["n"], scene["slug"]))
            if scene.get("summary"):
                lines.append("       %s" % scene["summary"])
            lines.append("       with: %s%s" % (
                who,
                "  thread: %s" % scene["thread"] if scene.get("thread") else "",
            ))
        lines.append("")
    return lines


def continuity(project):
    """Return a list of (severity, message) problems worth a writer's attention."""
    problems = []
    known = {c["name"].lower() for c in project.data["characters"]}
    thread_ids = {t["id"].lower() for t in project.data["threads"]}
    seen_threads = set()

    for ep in project.episodes_in():
        code = ep["code"]
        if not ep.get("logline"):
            problems.append(("warn", "%s has no logline" % code))
        if not ep.get("beats"):
            problems.append(("warn", "%s has no beat sheet (sf beats %s)" % (code, code)))
        if not ep.get("scenes"):
            problems.append(("warn", "%s has no scenes outlined" % code))
        for scene in ep.get("scenes") or []:
            if not scene.get("characters"):
                problems.append(("warn", "%s scene %d (%s) has nobody in it"
                                 % (code, scene["n"], scene["slug"])))
            for name in scene.get("characters") or []:
                if name.lower() not in known:
                    problems.append(("error", "%s scene %d references %r, who is not in the bible"
                                     % (code, scene["n"], name)))
            thread = scene.get("thread")
            if thread:
                seen_threads.add(thread.lower())
                if thread.lower() not in thread_ids:
                    problems.append(("error", "%s scene %d tracks unknown thread %r"
                                     % (code, scene["n"], thread)))
        path = project.draft_path(ep)
        if path.is_file():
            stats = fountain.stats(path.read_text(encoding="utf-8"))
            for speaker in stats["speakers"]:
                if speaker.lower() not in known:
                    problems.append(("error", "%s draft: %s speaks but is not in the bible"
                                     % (code, speaker)))
            target = project.data["format_minutes"]
            if stats["pages"] > target * 1.25:
                problems.append(("warn", "%s draft runs %.1f pages against a %d-minute format"
                                 % (code, stats["pages"], target)))

    for thread in project.data["threads"]:
        if thread["status"] == "open" and thread["id"].lower() not in seen_threads:
            problems.append(("warn", "thread %s (%s) is open but appears in no scene"
                             % (thread["id"], thread["name"])))

    for char in project.data["characters"]:
        appearances = sum(
            1 for ep in project.data["episodes"]
            for sc in ep.get("scenes") or []
            if char["name"].lower() in {n.lower() for n in sc.get("characters") or []}
        )
        if appearances == 0:
            problems.append(("warn", "%s is in the bible but appears nowhere"
                             % char["name"]))
    return problems


def stats_lines(project, episode_code=None):
    lines = []
    episodes = ([project.episode(episode_code)] if episode_code
                else project.episodes_in())
    total_pages = 0.0
    for ep in episodes:
        path = project.draft_path(ep)
        if not path.is_file():
            lines.append("%s  no draft yet" % ep["code"])
            continue
        s = fountain.stats(path.read_text(encoding="utf-8"))
        total_pages += s["pages"]
        ratio = 0 if not (s["dialogue_words"] + s["action_words"]) else (
            100.0 * s["dialogue_words"] / (s["dialogue_words"] + s["action_words"]))
        lines.append(
            "%s  %.1f pages (~%.1f min) | %d scenes | %d speeches | %.0f%% dialogue"
            % (ep["code"], s["pages"], s["pages"], s["scenes"], s["speeches"], ratio)
        )
        for name, count in sorted(s["speakers"].items(), key=lambda kv: -kv[1]):
            share = 100.0 * count / max(1, s["speeches"])
            label = "speech" if count == 1 else "speeches"
            lines.append("     %-20s %3d %-8s %5.1f%%" % (name, count, label, share))
    if len(episodes) > 1:
        lines.append("")
        lines.append("Total: %.1f pages across %d episodes" % (total_pages, len(episodes)))
    return lines
