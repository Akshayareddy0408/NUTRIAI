"""Dataset-backed discovery helpers. They never invent ingredients or nutrition values."""
import re
import pandas as pd

from .recommender import DIETS, diet_key, filter_diet
from .data_loader import food_to_dict

MOOD_RULES = {
    "comfort": {"keywords": ("khichdi", "porridge", "soup", "dal", "upma", "pulao"), "categories": {"breakfast", "lunch", "dinner", "lunch/dinner"}},
    "spicy": {"keywords": ("masala", "spicy", "chilli", "chili", "pepper", "curry"), "categories": {"lunch", "dinner", "lunch/dinner"}},
    "refreshing": {"keywords": ("salad", "raita", "lassi", "juice", "buttermilk", "fruit"), "categories": {"beverages", "snacks"}},
    "quick": {"keywords": ("sandwich", "toast", "poha", "upma", "omelette", "oats"), "categories": {"breakfast", "snacks"}},
    "protein": {"keywords": ("paneer", "chicken", "egg", "tofu", "dal", "chana", "rajma", "fish"), "categories": {"breakfast", "lunch", "dinner", "lunch/dinner"}},
}


def _diet(df, diet):
    if diet is not None and not isinstance(diet, str):
        raise ValueError("Choose a valid diet filter.")
    diet = diet_key(diet or "all")
    if diet not in DIETS and diet not in {"all", "egg"}:
        raise ValueError("Choose a valid diet filter.")
    return filter_diet(df, diet)


def _apply_preferences(items, preferences):
    if not isinstance(preferences, dict):
        return items
    def rank(item):
        rating = preferences.get(str(item.get("id")), "")
        return (0 if rating == "like" else 2 if rating == "dislike" else 1, item.get("name", "").casefold())
    return sorted(items, key=lambda item: (rank(item)[0], -item.get("match_count", 0), rank(item)[1]))


def pantry_matches(df, ingredients, diet="all", preferences=None):
    if not isinstance(ingredients, list) or not 1 <= len(ingredients) <= 30 or any(not isinstance(x, str) or len(x.strip()) > 60 for x in ingredients):
        raise ValueError("Enter between 1 and 30 ingredient names.")
    terms = list(dict.fromkeys(re.sub(r"\s+", " ", x).strip().casefold() for x in ingredients if x.strip()))
    if not terms:
        raise ValueError("Enter at least one ingredient.")
    pool = _diet(df, diet)
    results = []
    for idx, row in pool.iterrows():
        source = str(row["ingredients_text"]).casefold()
        matched = [term for term in terms if term in source]
        if matched:
            item = food_to_dict(row)
            item.update(matched_ingredients=matched, match_count=len(matched), ingredient_count=len([x for x in str(row["ingredients_text"]).split(";") if x.strip()]))
            results.append(item)
    results.sort(key=lambda x: (-x["match_count"], x["name"].casefold()))
    results = _apply_preferences(results, preferences)
    return {"matches": results[:20], "searched_ingredients": terms, "total_matches": len(results), "note": "Ingredient matching uses the dataset's listed ingredient text; check the recipe and packaging before cooking."}


def mood_matches(df, mood, diet="all", preferences=None):
    if not isinstance(mood, str) or mood not in MOOD_RULES:
        raise ValueError("Choose one of the available food moods.")
    rule = MOOD_RULES[mood]
    pool = _diet(df, diet)
    text = (pool["name"].fillna("") + " " + pool["ingredients_text"].fillna("")).str.casefold()
    category = pool["meal_category"].isin(rule["categories"])
    keyword = text.apply(lambda value: any(word in value for word in rule["keywords"]))
    hits = pool[category | keyword]
    items = [food_to_dict(row) for _, row in hits.iterrows()]
    items = _apply_preferences(items, preferences)
    return {"mood": mood, "matches": items[:20], "total_matches": int(len(hits)), "explanation": "Suggestions are matched using dish names, listed ingredients and meal categories in the catalog; this is a preference filter, not a health assessment."}


def substitute(df, food_id, diet="all"):
    if not isinstance(food_id, int) or food_id < 0 or food_id >= len(df):
        raise ValueError("Choose a valid dish.")
    original = df.loc[food_id]
    if str(original["nutrition_basis"]).strip().casefold() != "per serving (source)" or pd.isna(original["calories_kcal"]):
        raise ValueError("Substitution comparison is unavailable because this dish does not have comparable per-serving nutrition data.")
    pool = _diet(df, diet)
    pool = pool[(pool["meal_category"] == original["meal_category"]) & (pool.index != food_id)]
    pool = pool[(pool["nutrition_basis"].str.casefold() == "per serving (source)") & pool["calories_kcal"].notna()]
    if pool.empty:
        return {"original": food_to_dict(original), "alternatives": [], "note": "No comparable alternatives were found in this diet and meal category."}
    # Explainable, conservative ranking: compare only the four measured fields on the same serving basis.
    fields = ["calories_kcal", "protein_g", "carbohydrates_g", "fats_g", "fibre_g"]
    base = original[fields].astype(float)
    scales = pool[fields].std().replace(0, 1).fillna(1)
    distances = ((pool[fields].astype(float) - base) / scales).abs().mean(axis=1)
    ranked = pool.loc[distances.nsmallest(8).index]
    alternatives = []
    for idx, row in ranked.iterrows():
        item = food_to_dict(row)
        item["comparison"] = "Same meal category and diet filter; ranked by similarity across available per-serving calories, protein, carbohydrates, fat and fibre. This is not a claim of nutritional equivalence."
        alternatives.append(item)
    return {"original": food_to_dict(original), "alternatives": alternatives, "note": "Only comparable per-serving dataset records are considered. Check ingredients and allergens independently."}


def diversity_summary(plan):
    if not isinstance(plan, dict) or not isinstance(plan.get("days"), list):
        raise ValueError("Provide a generated weekly plan.")
    meals = [meal for day in plan["days"] if isinstance(day, dict) for meal in day.get("meals", []) if isinstance(meal, dict)]
    names = [str(m.get("name", "")) for m in meals]
    regions = {str(m.get("region", "")).strip() for m in meals if str(m.get("region", "")).strip()}
    categories = {str(m.get("category", "")).strip() for m in meals if str(m.get("category", "")).strip()}
    unique = len(set(names))
    return {"total_meals": len(meals), "unique_dishes": unique, "repeated_meals": len(names) - unique, "categories_represented": len(categories), "regions_represented": len(regions), "score": round(100 * unique / len(names)) if names else 0, "score_label": "unique-dish share", "note": "A descriptive variety indicator based only on dish names, categories and recorded regions; it is not a measure of diet quality."}


def nutrition_insights(plan):
    if not isinstance(plan, dict) or not isinstance(plan.get("days"), list) or not plan["days"]:
        raise ValueError("Generate a weekly plan before checking its nutrition data.")
    fields = {"calories": "calories", "protein": "protein", "carbohydrates": "carbs", "fat": "fat", "fibre": "fibre"}
    daily_rows = []
    missing = {key: 0 for key in fields}
    for day in plan["days"]:
        if not isinstance(day, dict) or not isinstance(day.get("meals", []), list):
            raise ValueError("The weekly plan contains an invalid day or meal list.")
        meals = day.get("meals", [])
        totals = {}
        for label, field in fields.items():
            values = [m.get(field) for m in meals if isinstance(m, dict) and isinstance(m.get(field), (int, float))]
            missing[label] += sum(1 for m in meals if not isinstance(m, dict) or not isinstance(m.get(field), (int, float)))
            totals[label] = round(sum(values), 1) if values else None
        daily_rows.append({"day": day.get("day", len(daily_rows) + 1), **totals})
    averages = {}
    for label in fields:
        values = [row[label] for row in daily_rows if row[label] is not None]
        averages[label] = round(sum(values) / len(values), 1) if values else None
    return {"daily_averages": averages, "days": daily_rows, "missing_values": missing, "note": "This checks only the completeness and variation of values in your selected dataset plan. It does not diagnose nutrient deficiencies or determine personal nutrition requirements."}
