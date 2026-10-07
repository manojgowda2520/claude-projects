"""Stage 4 - render one still per scene with the image model."""
import base64
import urllib.request

from .core import Project, client, load_config, say, step, warn

PRICE = {"dall-e-3": 0.040, "gpt-image-1": 0.042}


def _save(img, path):
    """Image endpoints return either a URL or inline base64 depending on model."""
    if getattr(img, "b64_json", None):
        path.write_bytes(base64.b64decode(img.b64_json))
    elif getattr(img, "url", None):
        with urllib.request.urlopen(img.url) as r:      # noqa: S310 - OpenAI CDN
            path.write_bytes(r.read())
    else:
        raise RuntimeError("image response contained neither url nor b64_json")


def run(slug, force=False):
    proj = Project(slug)
    cfg = load_config()
    data = proj.script()
    brief = proj.read_json(proj.brief_path)
    size = cfg["formats"][brief["format"]]["image_size"]
    model = cfg["models"]["image"]
    oa = client()

    step(f"Rendering {len(data['scenes'])} stills  [{model} @ {size}]")
    made = 0

    for sc in data["scenes"]:
        path = proj.images / f"scene_{sc['id']:02d}.png"
        if path.exists() and not force:
            say(f"scene {sc['id']:02d}  cached")
            continue

        prompt = f"{sc['visual_prompt']}. Style: {cfg['visual_style']}."
        try:
            kwargs = dict(model=model, prompt=prompt, size=size, n=1)
            if model == "dall-e-3":
                kwargs["quality"] = "standard"
            _save(oa.images.generate(**kwargs).data[0], path)
            made += 1
            say(f"scene {sc['id']:02d}  rendered")
        except Exception as e:                       # noqa: BLE001
            warn(f"scene {sc['id']:02d} failed: {type(e).__name__}: {e}")
            warn("assembly will hold the previous still over this scene")

    if made:
        proj.log_cost("visuals", made * PRICE.get(model, 0.04), f"{made} images")
    say(f"{made} new, {len(data['scenes']) - made} cached")
