import math
import random

MEAL_CATEGORIES = {
    "breakfast": {"breakfast"},
    "lunch": {"lunch", "lunch/dinner", "staple/any_meal"},
    "snack": {"snacks", "beverages", "desserts"},
    "dinner": {"dinner", "lunch/dinner", "staple/any_meal"},
}
SHARES = {"breakfast": .25, "lunch": .35, "snack": .10, "dinner": .30}
DIETS = {
    "vegetarian": {"vegetarian", "vegan"},
    "vegan": {"vegan"},
    "non-vegetarian": {"non-vegetarian"},
}
ACTIVITIES = {"low": 1.2, "light": 1.35, "moderate": 1.5, "high": 1.7}
GOALS = {"maintain": 0, "lose": -250, "gain": 250}


def diet_key(value):
    return value.strip().lower().replace("_", "-").replace(" ", "-")


def filter_diet(df, diet):
    if diet in ("", "all"):
        return df
    return df[df["diet_type"].isin(DIETS.get(diet, {diet}))]


def validate_profile(profile):
    if type(profile) is not dict:
        raise ValueError("Enter a valid profile.")
    validated = {}
    for key, low, high in (("age", 18, 100), ("height", 100, 230), ("weight", 25, 300)):
        try:
            value = float(profile.get(key))
        except (TypeError, ValueError, OverflowError):
            raise ValueError("Enter valid adult age, height and weight values.") from None
        if not math.isfinite(value) or not low <= value <= high:
            raise ValueError("Enter valid adult age, height and weight values.")
        validated[key] = value
    for key, default, options in (
        ("diet", "vegetarian", DIETS), ("activity", "moderate", ACTIVITIES),
        ("goal", "maintain", GOALS),
    ):
        value = profile.get(key, default)
        if isinstance(value, str) and key == "diet":
            value = diet_key(value)
        if not isinstance(value, str) or value not in options:
            raise ValueError(f"Choose a valid {key}.")
        validated[key] = value
    return validated


def target_calories(profile):
    baseline = 10 * profile["weight"] + 6.25 * profile["height"] - 5 * profile["age"] + 5
    estimate = baseline * ACTIVITIES[profile["activity"]] + GOALS[profile["goal"]]
    return max(1200, min(3500, round(estimate)))


def eligible_foods(df, profile):
    df = filter_diet(df, profile["diet"])
    return df[df["nutrition_basis"].eq("per serving (source)") & df["calories_kcal"].gt(0)]


def choose_pool(df, slot):
    return df[df["meal_category"].isin(MEAL_CATEGORIES[slot])]


def choose_meal(pool, slot, target, rng):
    distance = (pool["calories_kcal"] - target * SHARES[slot]).abs()
    shortlist = distance.nsmallest(5).index.to_list()
    row = pool.loc[rng.choice(shortlist)]
    return {
        "id": int(row.name), "slot": slot, "name": row["name"], "category": row["meal_category"],
        "diet": row["diet_type"], "calories": round(float(row["calories_kcal"]), 1),
        "protein": round(float(row["protein_g"]), 1),
        "carbs": round(float(row["carbohydrates_g"]), 1),
        "fat": round(float(row["fats_g"]), 1), "fibre": round(float(row["fibre_g"]), 1),
        "ingredients": row["ingredients_text"], "serving": row["serving_description"], "region": str(row.get("region", "") or ""),
    }


def recommend_week(df, profile, seed=None):
    rng = random.Random(seed)
    daily = target_calories(profile)
    eligible = eligible_foods(df, profile)
    pools = {slot: choose_pool(eligible, slot) for slot in SHARES}
    missing = [slot for slot, pool in pools.items() if pool.empty]
    if missing:
        raise ValueError(f"No matching dishes for {', '.join(missing)}.")
    used = set()
    week = []
    for day in range(1, 8):
        meals = []
        for slot, pool in pools.items():
            unseen = pool[~pool["name"].isin(used)]
            meal = choose_meal(unseen if not unseen.empty else pool, slot, daily, rng)
            used.add(meal["name"])
            meals.append(meal)
        week.append({"day": day, "meals": meals})
    return {"target_calories": daily, "days": week}


def swap_meal(df, current_name, slot, profile, seed=None, used_names=()):
    pool = choose_pool(eligible_foods(df, profile), slot)
    pool = pool[pool["name"].str.casefold() != current_name.strip().casefold()]
    if pool.empty:
        return None
    unseen = pool[~pool["name"].isin(used_names)]
    return choose_meal(unseen if not unseen.empty else pool, slot, target_calories(profile), random.Random(seed))
