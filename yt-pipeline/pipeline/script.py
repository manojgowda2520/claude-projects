"""Stage 1 - turn a topic into a structured, scene-broken script."""
import json

from .core import Project, client, load_config, say, step

SYSTEM = """You are a senior YouTube scriptwriter for a faceless channel. You write \
retention-first narration that sounds like a human being talking, not an article being read aloud.

Hard rules:
- The first sentence is the hook. It must create an open loop, a stakes statement, or a \
counterintuitive claim in under 12 words. Never open with a greeting, never say "in this video".
- Write for the ear. Short sentences. Contractions. Vary rhythm. No bullet-point voice.
- Every scene must advance the story. Cut anything that only restates.
- Do not invent specific statistics, dates, studies or quotes. If a number matters, speak \
qualitatively instead ("most", "a fraction of"). Accuracy beats specificity.
- No filler like "let's dive in", "buckle up", "the truth may shock you".
- End on a resolution of the opening loop, then the call to action, as the final scene.

For each scene also write:
- visual_prompt: a vivid, literal description of ONE still image. Describe subject, composition \
and lighting. It is rendered by an image model that cannot draw readable text, so never ask for \
words, letters, logos, charts with labels, or UI screenshots.
- on_screen_text: 2-5 words max, the punchy idea of that scene. May be empty string."""

USER = """Write a {fmt} YouTube video script.

TOPIC: {topic}
NICHE / CHANNEL ANGLE: {niche}
TARGET AUDIENCE: {audience}
TARGET LENGTH: about {seconds} seconds of spoken narration ({words} words total, spread over \
exactly {scenes} scenes)
CALL TO ACTION: {cta}

Return JSON with exactly this shape:
{{
  "title": "click-worthy YouTube title, under 60 characters, no clickbait lies",
  "hook": "the single opening line, repeated from scene 1 narration",
  "scenes": [
    {{"id": 1, "narration": "...", "visual_prompt": "...", "on_screen_text": "..."}}
  ],
  "description": "3-4 line YouTube description, first line carries the hook",
  "tags": ["10-15 lowercase search tags"],
  "thumbnail_idea": "one sentence describing the thumbnail image and its 3-word overlay"
}}"""

# Rough USD per 1k tokens; adjust if your pricing differs.
PRICE = {"in": 0.0025, "out": 0.010}


def run(slug, force=False):
    proj = Project(slug)
    if proj.script_path.exists() and not force:
        say("script.json already exists - skipping (use --force to regenerate)")
        return proj.script()

    brief = proj.read_json(proj.brief_path)
    cfg = load_config()
    fmt_cfg = cfg["formats"][brief["format"]]
    seconds = brief.get("seconds") or fmt_cfg["target_seconds"]
    scenes = brief.get("scenes") or fmt_cfg["scene_count"]

    step(f"Writing script: {brief['topic']}")
    say(f"format={brief['format']}  ~{seconds}s  {scenes} scenes")

    prompt = USER.format(
        fmt="short vertical" if brief["format"] == "short" else "long-form horizontal",
        topic=brief["topic"],
        niche=brief["niche"],
        audience=cfg["channel"]["audience"],
        seconds=seconds,
        words=int(seconds * 2.5),  # ~150 wpm narration
        scenes=scenes,
        cta=cfg["channel"]["cta"],
    )

    resp = client().chat.completions.create(
        model=cfg["models"]["script"],
        response_format={"type": "json_object"},
        temperature=0.85,
        messages=[{"role": "system", "content": SYSTEM},
                  {"role": "user", "content": prompt}],
    )
    data = json.loads(resp.choices[0].message.content)

    # normalise scene ids so downstream stages can rely on them
    for i, sc in enumerate(data.get("scenes", []), start=1):
        sc["id"] = i
        sc.setdefault("on_screen_text", "")

    proj.write_json(proj.script_path, data)

    u = resp.usage
    cost = (u.prompt_tokens / 1000 * PRICE["in"]) + (u.completion_tokens / 1000 * PRICE["out"])
    proj.log_cost("script", cost, f"{u.total_tokens} tokens")

    say(f"title: {data['title']}")
    say(f"hook : {data['hook']}")
    say(f"{len(data['scenes'])} scenes written  (~${cost:.3f})")
    return data
