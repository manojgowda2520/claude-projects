r"""Stage 5 - ffmpeg: ken-burns each still for its scene's duration, mux narration, burn captions.

All ffmpeg calls run with cwd set to the project folder and use relative paths. Windows
absolute paths (D:\...) break the subtitles filter, whose argument parser treats the drive
colon as a delimiter; relative paths sidestep the escaping problem entirely.
"""
import shutil

from .core import Project, ffmpeg, load_config, say, step, warn


def _kenburns(fmt, seconds, zoom_in):
    """Slow push in or out, then hard-scale to the output frame."""
    w, h, fps = fmt["width"], fmt["height"], fmt["fps"]
    frames = max(int(seconds * fps), 1)
    # oversample first so zoompan has real pixels to work with
    pre = (f"scale={w * 2}:{h * 2}:force_original_aspect_ratio=increase,"
           f"crop={w * 2}:{h * 2},setsar=1")
    if zoom_in:
        z = "min(zoom+0.00045,1.18)"
    else:
        z = "if(lte(zoom,1.0),1.18,max(zoom-0.00045,1.0))"
    zp = (f"zoompan=z='{z}':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
          f":s={w}x{h}:fps={fps}")
    return f"{pre},{zp},format=yuv420p"


def run(slug, force=False):
    proj = Project(slug)
    cfg = load_config()
    brief = proj.read_json(proj.brief_path)
    fmt = cfg["formats"][brief["format"]]
    timeline = proj.read_json(proj.dir / "timeline.json")
    if not timeline:
        from .core import die
        die("No timeline.json - run the 'voice' stage first.")

    if proj.final_path.exists() and not force:
        say("final.mp4 already exists - skipping (use --force to re-render)")
        return proj.final_path

    step("Assembling video")
    clips_dir = proj.render / "clips"
    clips_dir.mkdir(exist_ok=True)

    last_image = None
    clip_names = []

    for i, entry in enumerate(timeline["scenes"]):
        img = proj.images / f"scene_{entry['id']:02d}.png"
        if not img.exists():
            if last_image is None:
                warn(f"scene {entry['id']:02d} has no image and there is no earlier one to hold")
                continue
            img = last_image
            warn(f"scene {entry['id']:02d} using previous still")
        last_image = img

        clip = clips_dir / f"clip_{entry['id']:02d}.mp4"
        if not clip.exists() or force:
            ffmpeg([
                "-loop", "1", "-i", str(img.relative_to(proj.dir)),
                "-t", f"{entry['duration']:.3f}",
                "-vf", _kenburns(fmt, entry["duration"], zoom_in=(i % 2 == 0)),
                "-r", str(fmt["fps"]), "-c:v", "libx264", "-preset", "medium",
                "-crf", "20", "-pix_fmt", "yuv420p",
                str(clip.relative_to(proj.dir)),
            ], cwd=proj.dir)
        clip_names.append(clip.name)
        say(f"scene {entry['id']:02d}  {entry['duration']:5.2f}s")

    listing = clips_dir / "concat.txt"
    listing.write_text("".join(f"file '{n}'\n" for n in clip_names), encoding="utf-8")

    silent = proj.render / "silent.mp4"
    ffmpeg(["-f", "concat", "-safe", "0", "-i", "clips/concat.txt", "-c", "copy",
            "silent.mp4"], cwd=proj.render)

    # mux narration; -shortest guards against float drift between audio and video
    args = ["-i", "render/silent.mp4", "-i", "audio/voice.mp3"]
    ass = proj.dir / "captions.ass"
    if cfg["captions"]["enabled"] and ass.exists():
        args += ["-vf", "ass=captions.ass",
                 "-c:v", "libx264", "-preset", "medium", "-crf", "20"]
        say("burning captions")
    else:
        args += ["-c:v", "copy"]
    args += ["-c:a", "aac", "-b:a", "192k", "-shortest", "render/final.mp4"]
    ffmpeg(args, cwd=proj.dir)

    silent.unlink(missing_ok=True)
    shutil.rmtree(clips_dir, ignore_errors=True)

    size_mb = proj.final_path.stat().st_size / 1_000_000
    say(f"done: {proj.final_path}  ({size_mb:.1f} MB, {timeline['total_seconds']}s)")
    return proj.final_path
