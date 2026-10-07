# Faceless YouTube pipeline

Topic in, finished MP4 out. One OpenAI key covers script, voiceover, visuals and caption timing.

## Setup

    pip install -r requirements.txt
    copy .env.example .env      # then paste your key into .env
    python run.py doctor        # checks ffmpeg, key, and model access

ffmpeg and ffprobe must be on PATH.

## Use

    python run.py new "Why deep sea creatures glow" --niche "ocean science" --format short
    python run.py make why-deep-sea-creatures-glow

    python run.py batch topics.txt --niche "ocean science"   # one topic per line
    python run.py list

Formats: `short` = 1080x1920, ~45s, 5 scenes. `long` = 1920x1080, ~8min, 14 scenes.

## Stages

Every stage caches its output. Rerunning skips finished work; `--force` redoes it.
Run a subset with `--only`, e.g. `--only script` to read the script before paying for the rest.

| Stage | Does | Writes |
|---|---|---|
| script | GPT writes a hook-first, scene-broken script | `script.json` |
| voice | TTS narrates each scene, then one master track | `audio/`, `timeline.json` |
| captions | Whisper transcribes our own audio for exact word timings | `captions.srt`, `captions.ass` |
| visuals | One still per scene from the image model | `images/` |
| assemble | Ken-burns each still for its scene length, mux audio, burn captions | `render/final.mp4` |

Scene durations come from the real narration audio, so picture and voice cannot drift.

## Cost

Tracked per project in `costs.json`. A 45s short runs roughly $0.25-0.35, almost all of it
image generation. Drop `scene_count` or reuse stills to cut it.

## Tuning

`config.json` holds models, voice, visual style, caption styling and format specs.
- Different look: rewrite `visual_style`.
- Different read: change `voice` (alloy, echo, fable, onyx, nova, shimmer) and `voice_instructions`.
- Model access varies by account. `python run.py doctor` reports which configured models your key can actually see; swap any that come back unavailable.

The script prompt in `pipeline/script.py` is the highest-leverage thing to edit. It controls
hook style, pacing and structure - that is what retention lives or dies on.

## Captions

Burn-in uses `captions.ass`, not the SRT. ASS carries an explicit PlayResX/PlayResY, so
FontSize and MarginV are real output pixels. SRT with `force_style` silently renders against a
small default canvas and large margins push the text off screen. The SRT is still written, for
uploading to YouTube as a selectable subtitle track.

## Before you publish

The script stage is instructed not to invent statistics, but read every script anyway.
`--only script` exists for that. YouTube demonetises mass-produced, unreviewed content, so the
pipeline is built to make your review the cheap step, not to remove it.
