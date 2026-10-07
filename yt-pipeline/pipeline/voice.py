"""Stage 2 - narrate each scene with OpenAI TTS, then stitch one master track."""
from .core import Project, audio_duration, client, ffmpeg, load_config, say, step, warn

PRICE_PER_1K_CHARS = 0.015


def _speak(oa, cfg, text, out_path):
    """Try the configured TTS model, fall back if the account lacks access."""
    models = [cfg["models"]["tts"], cfg["models"].get("tts_fallback", "tts-1")]
    last_err = None
    for model in models:
        kwargs = dict(model=model, voice=cfg["voice"], input=text)
        if model.startswith("gpt-4o"):
            kwargs["instructions"] = cfg["voice_instructions"]
        try:
            with oa.audio.speech.with_streaming_response.create(**kwargs) as resp:
                resp.stream_to_file(out_path)
            return model
        except Exception as e:                      # noqa: BLE001 - report and try next
            last_err = e
            warn(f"TTS model '{model}' failed ({type(e).__name__}), trying next")
    raise RuntimeError(f"All TTS models failed. Last error: {last_err}")


def run(slug, force=False):
    proj = Project(slug)
    cfg = load_config()
    data = proj.script()
    oa = client()

    step("Recording narration")
    timeline, chars = [], 0

    for sc in data["scenes"]:
        clip = proj.audio / f"scene_{sc['id']:02d}.mp3"
        if not clip.exists() or force:
            model = _speak(oa, cfg, sc["narration"], clip)
            chars += len(sc["narration"])
            say(f"scene {sc['id']:02d}  {len(sc['narration']):4d} chars  [{model}]")
        else:
            say(f"scene {sc['id']:02d}  cached")
        timeline.append({"id": sc["id"], "file": clip.name,
                         "duration": round(audio_duration(clip), 3)})

    # concat into one master track ffmpeg can mux against the visuals
    listing = proj.audio / "concat.txt"
    listing.write_text("".join(f"file '{t['file']}'\n" for t in timeline), encoding="utf-8")
    ffmpeg(["-f", "concat", "-safe", "0", "-i", "concat.txt",
            "-c:a", "libmp3lame", "-b:a", "192k", "voice.mp3"], cwd=proj.audio)

    total = round(audio_duration(proj.voice_path), 2)
    proj.write_json(proj.dir / "timeline.json", {"total_seconds": total, "scenes": timeline})

    if chars:
        proj.log_cost("voice", chars / 1000 * PRICE_PER_1K_CHARS, f"{chars} chars")
    say(f"narration total: {total}s")
    return timeline
