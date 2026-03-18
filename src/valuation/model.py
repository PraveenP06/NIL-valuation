import os
import sys
import math

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from db.models import Player, SocialMedia, PerformanceStats

# ---------------------------------------------------------------------------
# Position & conference multipliers
# ---------------------------------------------------------------------------

POSITION_MULTIPLIERS: dict[str, float] = {
    "QB": 1.5, "WR": 1.2, "TE": 1.1, "RB": 1.0,
    "LB": 0.9, "DL": 0.85, "DE": 0.85, "DT": 0.85,
    "DB": 0.8, "CB": 0.8, "S": 0.8, "SS": 0.8, "FS": 0.8,
    "K": 0.7, "P": 0.7,
}

CONFERENCE_MULTIPLIERS: dict[str, float] = {
    "SEC": 1.3,
    "Big Ten": 1.2,
    "ACC": 1.0,
    "Big 12": 0.95,
}

# Class year → score (0-100). JR peak NIL — proven on field, NFL hype.
CLASS_YEAR_SCORES: dict[int, float] = {
    1: 50.0,   # FR: unproven
    2: 70.0,   # SO: developing
    3: 90.0,   # JR: peak NIL, proven + NFL spotlight
    4: 75.0,   # SR: proven but last year of eligibility
}

# Non-skill positions that don't accumulate yards/TDs
NON_SKILL_POSITIONS = {"OL", "OT", "OG", "C", "DL", "DT", "DE", "EDGE", "NT", "LB", "ILB", "OLB", "K", "P", "LS"}

# Tier 1: elite programs (90–100 base school score)
TIER1_SCHOOLS = {
    "Alabama", "Ohio State", "Georgia", "Michigan", "Texas",
    "Notre Dame", "Clemson", "LSU", "Oklahoma", "Penn State",
    "Florida", "Tennessee", "Auburn", "USC", "Oregon",
    "Miami", "Florida State", "Texas A&M", "Wisconsin", "Iowa",
}

# Tier 2: solid Power 4 programs (70–89)
TIER2_SCHOOLS = {
    "Mississippi State", "Ole Miss", "Arkansas", "Kentucky", "Vanderbilt",
    "South Carolina", "Missouri", "Indiana", "Purdue", "Illinois",
    "Minnesota", "Nebraska", "Maryland", "Rutgers", "Michigan State",
    "North Carolina", "Virginia Tech", "Pittsburgh", "Duke", "Wake Forest",
    "North Carolina State", "Syracuse", "Boston College", "Louisville",
    "Virginia", "Kansas State", "Baylor", "TCU", "Iowa State",
    "West Virginia", "Texas Tech", "Oklahoma State", "Kansas", "Cincinnati",
    "UCF", "Houston", "BYU",
}

# Conference fallback school score if school not found in tiers
CONFERENCE_SCHOOL_FALLBACK: dict[str, float] = {
    "SEC": 80.0,
    "Big Ten": 78.0,
    "ACC": 72.0,
    "Big 12": 70.0,
}


# ---------------------------------------------------------------------------
# Scoring functions
# ---------------------------------------------------------------------------

def calculate_performance_score(stats: PerformanceStats | None, position: str | None = None) -> float:
    """Return a 0–100 performance score."""
    if stats is None:
        return 0.0

    CAPS = {
        "total_yards": 1800.0,
        "touchdowns": 20.0,
        "efficiency_metric": 200.0,
        "yards_per_game": 150.0,
        "team_wins": 13.0,
    }
    WEIGHTS = {
        "total_yards": 0.30,
        "touchdowns": 0.25,
        "efficiency_metric": 0.20,
        "yards_per_game": 0.15,
        "team_wins": 0.10,
    }

    present: dict[str, float] = {}
    for field, cap in CAPS.items():
        val = getattr(stats, field, None)
        if val is not None:
            present[field] = min(float(val), cap) / cap * 100.0

    if not present:
        # Non-skill positions (OL, DL, LB, etc.) have no yards/TDs.
        # Score them on team wins + usage share instead.
        pos = (position or "").upper().strip()
        if pos in NON_SKILL_POSITIONS or pos == "":
            team_wins = getattr(stats, "team_wins", None)
            usage = getattr(stats, "usage_share", None)
            wins_score = min(float(team_wins or 0), 13.0) / 13.0 * 100.0
            usage_score = min(float(usage or 0), 1.0) * 100.0
            if usage is not None:
                return round(wins_score * 0.6 + usage_score * 0.4, 2)
            return round(wins_score * 0.7, 2)
        return 0.0

    # Redistribute weight proportionally among present fields
    total_weight = sum(WEIGHTS[f] for f in present)
    score = sum(present[f] * (WEIGHTS[f] / total_weight) for f in present)
    return round(score, 2)


def calculate_class_year_score(player: Player) -> float:
    """Return a 0–100 class year score. Juniors peak — proven + NFL spotlight."""
    cy = getattr(player, "class_year", None)
    return CLASS_YEAR_SCORES.get(cy, 65.0)  # 65 = unknown/default


def calculate_social_score(social: SocialMedia | None, cap: int = 3_000_000) -> float:
    """Return a 0–100 social score with engagement and verification bonuses."""
    if social is None:
        return 0.0

    followers = getattr(social, "total_followers", None) or 0
    if followers <= 0:
        base = 0.0
    else:
        base = math.log10(min(followers, cap)) / math.log10(cap) * 100.0

    # Engagement bonus: up to +10 for high engagement_rate (treated as %)
    engagement = getattr(social, "engagement_rate", None)
    bonus = 0.0
    if engagement and engagement > 0:
        # 5% engagement → full +10 bonus
        bonus += min(engagement / 5.0, 1.0) * 10.0

    # Verification bonus
    if getattr(social, "verified_instagram", False):
        bonus += 3.0

    return round(min(base + bonus, 100.0), 2)


def calculate_school_score(player: Player) -> float:
    """Return a 0–100 school prestige score."""
    school = (player.school or "").strip()
    if school in TIER1_SCHOOLS:
        return 95.0
    if school in TIER2_SCHOOLS:
        return 75.0
    # G5 fallback via conference
    conf = (player.conference or "").strip()
    return CONFERENCE_SCHOOL_FALLBACK.get(conf, 50.0)


def get_position_multiplier(position: str | None) -> float:
    """Return a 0.7–1.5 position multiplier."""
    if not position:
        return 1.0
    return POSITION_MULTIPLIERS.get(position.upper().strip(), 1.0)


def get_conference_multiplier(conference: str | None) -> float:
    """Return a 0.8–1.3 conference multiplier."""
    if not conference:
        return 0.8
    return CONFERENCE_MULTIPLIERS.get(conference.strip(), 0.8)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def estimate_nil_value(
    player: Player,
    stats: PerformanceStats | None,
    social: SocialMedia | None,
    base_value: float = 10_000.0,
    social_cap: int = 500_000,
) -> dict:
    """
    Compute NIL value and return a dict with nil_value + all component scores.

    Formula:
        nil_value = (perf*0.30 + social*0.25 + school*0.20
                     + pos_mult*0.15 + conf_mult*0.10) * base_value
    """
    perf_score    = calculate_performance_score(stats, position=player.position)
    social_score  = calculate_social_score(social, cap=social_cap)
    school_score  = calculate_school_score(player)
    class_score   = calculate_class_year_score(player)
    pos_mult      = get_position_multiplier(player.position)
    conf_mult     = get_conference_multiplier(player.conference)

    # Normalise multipliers [min,max] → [0,100] so all components share the same scale
    pos_score  = (pos_mult  - 0.7) / (1.5 - 0.7) * 100.0
    conf_score = (conf_mult - 0.8) / (1.3 - 0.8) * 100.0

    # Weights: perf 25%, social 25%, school 20%, position 15%, conference 10%, class year 5%
    composite = (
        perf_score   * 0.25
        + social_score * 0.25
        + school_score * 0.20
        + pos_score    * 0.15
        + conf_score   * 0.10
        + class_score  * 0.05
    )

    nil_value = round(composite / 100.0 * base_value, 2)

    return {
        "player_id":      player.id,
        "season":         player.season,
        "nil_value":      nil_value,
        "perf_score":     perf_score,
        "social_score":   social_score,
        "school_score":   school_score,
        "class_score":    class_score,
        "position_mult":  pos_mult,
        "conference_mult": conf_mult,
    }
