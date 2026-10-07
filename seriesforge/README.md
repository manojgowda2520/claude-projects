# SeriesForge

A writers' room in a CLI, for episodic television. Keeps a series bible, beat
sheets, scene cards and Fountain drafts in one plain-text project you can commit
to git — and checks them against each other.

Pure standard-library Python 3.9+. No dependencies.

## Install

```bash
pip install -e D:\Claude\seriesforge
```

That puts an `sf` command on your PATH. Without installing, run it as
`python -m seriesforge` from anywhere with `PYTHONPATH=D:\Claude\seriesforge`.

## The shape of a project

`sf init` writes `seriesforge.json` in the current folder; every later command
finds it by walking up from the working directory (or by `SERIESFORGE_PROJECT`).
Drafts live beside it in `drafts/S01E01.fountain`.

```
my-series/
  seriesforge.json     bible, threads, episodes, beats, scene cards
  drafts/
    S01E01.fountain    the script you actually write in
```

## A full pass

```bash
sf init "Signal Loss" --genre thriller --minutes 45 \
  --logline "An engineer hears a broadcast from a town that no longer exists."

sf character add "MARA OKOYE" --role lead \
  --want "to prove the signal is real" --need "to forgive herself" \
  --flaw "cannot let anything go"
sf character add "DEV" --role foil --want "his friend back"
sf location add "The relay station" --description "Cold war era, one window"
sf thread add the-tape --name "The tape" --introduced S1E1

sf episode add S1E1 --title "Static" --logline "Mara picks up a broadcast that should not exist."
sf beats S1E1 --structure five-act
sf beat S1E1 Teaser --note "3am. The signal cuts through. She is alone." --done

sf scene add S1E1 "INT. RELAY STATION - NIGHT" \
  --summary "Mara hears the broadcast" --characters "MARA OKOYE" \
  --thread the-tape --value "boredom -> dread"
sf scene add S1E1 "EXT. PIER - DAWN" --summary "Dev refuses to believe her" \
  --characters "MARA OKOYE,DEV" --thread the-tape

sf draft S1E1          # scaffolds drafts/S01E01.fountain from the outline
# ...write...
sf stats S1E1
sf continuity
sf export S1E1 --format text --out out/S01E01.txt
```

## Commands

| Command | What it does |
| --- | --- |
| `sf init TITLE` | Start a project (`--genre --logline --minutes --path`) |
| `sf character add\|list` | Series bible: name, role, want, need, flaw, arc, voice |
| `sf location add\|list` | Standing sets |
| `sf thread add\|list\|resolve` | Serialised threads, with the episode they close in |
| `sf season add N` | Season title, theme, arc |
| `sf episode add\|set CODE` | Episodes, addressed as `S1E2` / `s01e02` |
| `sf beats CODE --structure X` | Lay a beat structure over an episode |
| `sf beat CODE NAME --note --done` | Fill in one beat |
| `sf scene add\|move\|remove` | Scene cards; renumbered automatically |
| `sf draft CODE` | Generate the Fountain draft from the outline (`--force` to redo) |
| `sf export CODE --format text\|fountain\|outline` | Export, to stdout or `--out FILE` |
| `sf outline [CODE] [--season N]` | The outline as text |
| `sf status` | Dashboard: beat progress, page count, scene count per episode |
| `sf stats [CODE]` | Pages, runtime estimate, dialogue share, who speaks most |
| `sf continuity` | Cross-checks (exit code 1 if any errors) |
| `sf structures` | List the beat structures with their prompts |

## Beat structures

`five-act` (Teaser / Act One–Four / Tag — the TV default), `three-act`,
`harmon` (the story circle), `kishotenketsu` (four-act, twist rather than
conflict), and `pilot` (a checklist specific to first episodes).

## What `sf continuity` checks

- Characters who speak in a draft or appear on a scene card but are not in the bible
- Scene cards tagged with a thread that does not exist
- Threads still open that appear in no scene; characters in the bible who appear nowhere
- Episodes with no logline, no beat sheet, or no scenes
- Drafts running more than 25% over the series' target format length

## Drafting

`sf draft` writes a Fountain file seeded from your scene cards: scene headings in
order, each summary as a `[[note]]`, and a blank character cue for everyone the
card says is in the scene. You write between them in any editor.

Page counts use the standard 55-lines-per-page approximation, so one page is
roughly one minute of screen time. Notes and boneyard comments are excluded from
the count and from the `text` export.

## Tests

```bash
python D:\Claude\seriesforge\tests\test_seriesforge.py
```
