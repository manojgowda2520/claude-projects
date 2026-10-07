"""Beat-sheet structures. Each is an ordered list of (name, prompt) pairs."""

from seriesforge.errors import SeriesForgeError

STRUCTURES = {
    "five-act": [
        ("Teaser", "The cold open. A hook that poses the episode's question."),
        ("Act One", "Establish the want. Something knocks the status quo over."),
        ("Act Two", "Complications. The easy plan fails; the cost rises."),
        ("Act Three", "Midpoint reversal. What they wanted is not what they need."),
        ("Act Four", "Crisis and climax. The choice that proves the change."),
        ("Tag", "The button. New status quo, or the hook into next episode."),
    ],
    "three-act": [
        ("Setup", "Ordinary world and the standing want."),
        ("Inciting Incident", "The intrusion that makes the episode necessary."),
        ("Lock-In", "The point of no return."),
        ("Midpoint", "A reversal that redefines the goal."),
        ("Crisis", "The worst option versus the other worst option."),
        ("Climax", "The active choice and its immediate cost."),
        ("Resolution", "The new equilibrium."),
    ],
    "harmon": [
        ("You", "A character in a zone of comfort."),
        ("Need", "But they want something."),
        ("Go", "They enter an unfamiliar situation."),
        ("Search", "Adapt to it."),
        ("Find", "Get what they wanted."),
        ("Take", "Pay a heavy price for it."),
        ("Return", "Then return to their familiar situation."),
        ("Change", "Having changed."),
    ],
    "kishotenketsu": [
        ("Ki", "Introduction. Establish people and place without conflict."),
        ("Sho", "Development. Deepen, do not escalate."),
        ("Ten", "Twist. An unforeseen element recontextualises the rest."),
        ("Ketsu", "Conclusion. The twist settles into meaning."),
    ],
    "pilot": [
        ("Hook", "The image that sells the series in sixty seconds."),
        ("Ordinary World", "The rules of this world, dramatised not explained."),
        ("Cast Introductions", "Every regular, with a want visible on arrival."),
        ("Promise of the Premise", "The scene a viewer tuned in hoping to see."),
        ("The Engine", "Prove the machine that generates episode after episode."),
        ("Series Question", "The question the season will answer."),
        ("Button", "The turn that makes episode two unavoidable."),
    ],
}


def get_structure(name):
    key = (name or "").strip().lower()
    if key not in STRUCTURES:
        raise SeriesForgeError(
            "unknown structure %r; choose from: %s"
            % (name, ", ".join(sorted(STRUCTURES)))
        )
    return [{"name": n, "prompt": p, "note": "", "done": False} for n, p in STRUCTURES[key]]
