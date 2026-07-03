def compute_cost_report(decisions: list[dict], hourly_rate: int = 100) -> dict:
    total_tokens = sum(d.get("token_cost", 0) for d in decisions)
    total_spend = round(total_tokens, 2)

    time_saved_minutes = 0
    for d in decisions:
        action = d.get("action", "")
        outcome = d.get("outcome", "")
        cat = d.get("category", "")
        if outcome == "resolved":
            if action == "auto_rerun" or cat == "flake":
                time_saved_minutes += 5
            elif action == "suggest_fix":
                time_saved_minutes += 10

    dollar_value = round((time_saved_minutes / 60) * hourly_rate, 2)
    multiplier = round(dollar_value / total_spend, 2) if total_spend > 0 else 0

    by_category = {}
    for d in decisions:
        cat = d.get("category", "unknown")
        cost = d.get("token_cost", 0)
        by_category[cat] = round(by_category.get(cat, 0) + cost, 2)

    return {
        "total_spend": total_spend,
        "time_saved_minutes": time_saved_minutes,
        "dollar_value": dollar_value,
        "multiplier": multiplier,
        "by_category": by_category,
    }
