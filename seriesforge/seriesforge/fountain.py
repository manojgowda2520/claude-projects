"""Fountain scaffolding, light parsing, and plain-text screenplay rendering.

Fountain is the plain-text screenplay format (fountain.io). We only implement
the subset a working draft needs: title page, scene headings, action,
character cues, parentheticals, dialogue, transitions and notes.
"""

import re

SCENE_PREFIXES = ("INT.", "EXT.", "INT/EXT.", "I/E.", "EST.")
TRANSITION_RE = re.compile(r"^[A-Z0-9 ]+ TO:$")
# 1 screenplay page is roughly 55 lines of a 12pt courier page.
LINES_PER_PAGE = 55


def is_scene_heading(line):
    stripped = line.strip()
    if stripped.startswith("."):
        return len(stripped) > 1 and not stripped.startswith("..")
    upper = stripped.upper()
    return any(upper.startswith(p) for p in SCENE_PREFIXES)


def is_transition(line):
    stripped = line.strip()
    return bool(TRANSITION_RE.match(stripped)) or stripped.startswith(">")


def is_character_cue(line, previous, following):
    """A cue is an all-caps line, preceded by blank, followed by content."""
    stripped = line.strip()
    if not stripped or previous.strip() or not following.strip():
        return False
    if is_scene_heading(stripped) or is_transition(stripped):
        return False
    if stripped.startswith("@"):
        return True
    core = re.sub(r"\(.*?\)", "", stripped).strip()
    if not core or not re.search(r"[A-Z]", core):
        return False
    return core == core.upper() and not core.endswith((".", "?", "!"))


def cue_name(line):
    return re.sub(r"\(.*?\)", "", line.strip().lstrip("@")).strip().rstrip("^").strip()


def scaffold(project, episode):
    """Build the starting .fountain text for an episode from its outline."""
    data = project.data
    out = [
        "Title: %s" % (episode.get("title") or episode["code"]),
        "Series: %s" % data["title"],
        "Episode: %s" % episode["code"],
        "Draft date: ",
        "",
        "",
    ]
    if episode.get("logline"):
        out += ["/* LOGLINE: %s */" % episode["logline"], ""]

    beats = episode.get("beats") or []
    scenes = episode.get("scenes") or []
    if not scenes:
        out += ["/* No scenes outlined yet. Run `sf scene add %s ...` and"
                " regenerate, or write straight into this file. */" % episode["code"], ""]
        for beat in beats:
            out += [".%s" % beat["name"].upper(), "", "[[%s]]" % (beat.get("note") or beat["prompt"]), ""]
        return "\n".join(out) + "\n"

    for scene in scenes:
        out.append(scene["slug"].upper())
        out.append("")
        note = scene.get("summary") or ""
        if scene.get("value_shift"):
            note = ("%s (value: %s)" % (note, scene["value_shift"])).strip()
        if note:
            out += ["[[%s]]" % note, ""]
        for name in scene.get("characters") or []:
            out += [name.upper(), "", ""]
    return "\n".join(out) + "\n"


def stats(text):
    """Return counts derived from a fountain draft."""
    lines = text.splitlines()
    body_start = 0
    for i, line in enumerate(lines):
        if not line.strip():
            body_start = i
            break
    body = lines[body_start:]

    scenes, cues, dialogue_words, action_words = 0, [], 0, 0
    in_dialogue = False
    for i, line in enumerate(body):
        previous = body[i - 1] if i else ""
        following = body[i + 1] if i + 1 < len(body) else ""
        stripped = line.strip()
        if not stripped:
            in_dialogue = False
            continue
        if stripped.startswith(("/*", "[[")) or stripped.endswith("*/"):
            continue
        if is_scene_heading(stripped):
            scenes += 1
            in_dialogue = False
        elif is_character_cue(line, previous, following):
            cues.append(cue_name(line))
            in_dialogue = True
        elif in_dialogue:
            dialogue_words += len(stripped.split())
        else:
            action_words += len(stripped.split())

    speakers = {}
    for name in cues:
        speakers[name] = speakers.get(name, 0) + 1
    return {
        "scenes": scenes,
        "speeches": len(cues),
        "speakers": speakers,
        "dialogue_words": dialogue_words,
        "action_words": action_words,
        "pages": round(max(1, len([l for l in body if l.strip()])) / LINES_PER_PAGE, 1),
    }


def _blank(out):
    """Append a single separating blank line, never two in a row."""
    if out and out[-1] != "":
        out.append("")


def render_text(text, width=60):
    """Render fountain as an indented, courier-style plain-text screenplay."""
    lines = text.splitlines()
    out = []
    started = False
    in_dialogue = False
    for i, line in enumerate(lines):
        previous = lines[i - 1] if i else ""
        following = lines[i + 1] if i + 1 < len(lines) else ""
        stripped = line.strip()
        if not started:
            if re.match(r"^[A-Za-z ]+:", stripped):
                out.append(stripped)
                continue
            if not stripped:
                continue
            started = True
        if stripped.startswith(("[[", "/*")) or stripped.endswith("*/"):
            continue
        if not stripped:
            in_dialogue = False
            if out and out[-1] != "":
                out.append("")
            continue
        if is_scene_heading(stripped):
            in_dialogue = False
            _blank(out)
            out.append(stripped.lstrip(".").upper())
        elif is_transition(stripped):
            in_dialogue = False
            _blank(out)
            out.append(stripped.lstrip(">").strip().upper().rjust(width + 15))
        elif is_character_cue(line, previous, following):
            in_dialogue = True
            _blank(out)
            out.append(" " * 22 + cue_name(line).upper())
        elif in_dialogue and stripped.startswith("(") and stripped.endswith(")"):
            out.append(" " * 16 + stripped)
        elif in_dialogue:
            out.append(" " * 10 + stripped)
        else:
            out.append(stripped)
    return "\n".join(out).strip() + "\n"
