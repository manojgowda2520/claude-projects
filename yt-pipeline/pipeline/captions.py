"""Stage 3 - transcribe the generated voice track and build caption files.

We transcribe our own TTS output rather than time the script by hand: the word timings
come back exact, so captions never drift.

Two files are written:
  captions.srt - plain, for uploading to YouTube as a subtitle track
  captions.ass - styled, for burning in. ASS carries an explicit PlayResX/PlayResY, so
                 FontSize and MarginV are real output pixels. (SRT + force_style does not:
                 libass falls back to a small default canvas and large margins throw the
                 text clean off screen.)
"""
from .core import Project, audio_duration, client, load_config, say, step

PRICE_PER_MIN = 0.006

ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{size},{primary},&H000000FF,{outline},&H00000000,-1,0,0,0,100,100,0,0,1,{border},2,2,{side},{side},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _srt_time(seconds):
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _ass_time(seconds):
    cs = int(round(seconds * 100))
    h, cs = divmod(cs, 360_000)
    m, cs = divmod(cs, 6_000)
    s, cs = divmod(cs, 100)
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


def _group(words, max_words):
    """Chunk words into short cues, breaking early on sentence-ending punctuation."""
    cues, buf = [], []
    for w in words:
        buf.append(w)
        if len(buf) >= max_words or w["word"].strip().endswith((".", "!", "?", ":")):
            cues.append(buf)
            buf = []
    if buf:
        cues.append(buf)
    return cues


def run(slug, force=False):
    proj = Project(slug)
    cfg = load_config()
    if not cfg["captions"]["enabled"]:
        say("captions disabled in config - skipping")
        return None

    ass_path = proj.dir / "captions.ass"
    if ass_path.exists() and not force:
        say("captions already exist - skipping")
        return ass_path

    step("Transcribing narration for captions")
    with open(proj.voice_path, "rb") as fh:
        result = client().audio.transcriptions.create(
            model=cfg["models"]["transcribe"], file=fh,
            response_format="verbose_json", timestamp_granularities=["word"])

    words = [{"word": w.word, "start": w.start, "end": w.end}
             for w in (getattr(result, "words", None) or [])]
    if not words:
        say("no word timings returned - captions skipped")
        return None

    brief = proj.read_json(proj.brief_path)
    fmt = cfg["formats"][brief["format"]]
    c = cfg["captions"]
    short = brief["format"] == "short"
    cues = _group(words, c["max_words_per_cue"])

    srt_lines, ass_lines = [], []
    for i, cue in enumerate(cues, start=1):
        text = " ".join(w["word"] for w in cue).strip().upper()
        start, end = cue[0]["start"], cue[-1]["end"]
        srt_lines.append(f"{i}\n{_srt_time(start)} --> {_srt_time(end)}\n{text}\n")
        ass_lines.append(
            f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Default,,0,0,0,,{text}")

    proj.captions_path.write_text("\n".join(srt_lines), encoding="utf-8")
    header = ASS_HEADER.format(
        w=fmt["width"], h=fmt["height"],
        font=c.get("font", "Arial Black"),
        size=c["font_size_short"] if short else c["font_size_long"],
        primary=c["primary_colour"], outline=c["outline_colour"],
        border=c.get("outline_width", 4),
        side=int(fmt["width"] * 0.08),
        margin_v=c["margin_v_short"] if short else c["margin_v_long"])
    ass_path.write_text(header + "\n".join(ass_lines) + "\n", encoding="utf-8")

    proj.log_cost("captions", audio_duration(proj.voice_path) / 60 * PRICE_PER_MIN)
    say(f"{len(cues)} caption cues written (.srt + .ass)")
    return ass_path
