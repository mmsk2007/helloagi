from dataclasses import dataclass


@dataclass
class CharacterSeed:
    mission: str
    style: str
    domain_focus: str


def build_initial_character(seed: CharacterSeed) -> dict:
    archetype = "Systems Sage"
    if "growth" in seed.mission.lower() or "market" in seed.domain_focus.lower():
        archetype = "Growth Architect"
    if "research" in seed.style.lower() or "science" in seed.domain_focus.lower():
        archetype = "Research Strategist"

    principles = [
        "Pursue truth through measurable evidence",
        "Convert ideas into testable systems",
        "Stay aligned with human intent and safety boundaries",
    ]

    return {
        "archetype": archetype,
        "mission": seed.mission,
        "style": seed.style,
        "domain_focus": seed.domain_focus,
        "principles": principles,
    }
