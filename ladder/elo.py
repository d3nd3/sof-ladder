def k_factor(games_played: int, elo: int) -> int:
    if elo >= 2000:
        return 12
    if games_played < 10:
        return 40
    if games_played < 30:
        return 32
    return 16


def expected_score(ra: int, rb: int) -> float:
    return 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))


def apply_elo(
    ra: int, rb: int, score_a: float, games_a: int, games_b: int
) -> tuple[int, int, int, int, int, int]:
    """Returns (new_a, new_b, delta_a, delta_b, k_a, k_b). score_a in {0, 0.5, 1}."""
    ka, kb = k_factor(games_a, ra), k_factor(games_b, rb)
    ea, eb = expected_score(ra, rb), expected_score(rb, ra)
    da = round(ka * (score_a - ea))
    db = round(kb * ((1.0 - score_a) - eb))
    return ra + da, rb + db, da, db, ka, kb
