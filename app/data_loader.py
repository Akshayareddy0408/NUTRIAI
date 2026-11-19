from functools import lru_cache

import pandas as pd

from .recommender import diet_key

NUTRIENTS = {
    "calories": "calories_kcal", "protein": "protein_g", "carbs": "carbohydrates_g",
    "fat": "fats_g", "fibre": "fibre_g",
}


@lru_cache(maxsize=4)
def load_foods(path):
    df = pd.read_csv(path, encoding="utf-8", keep_default_na=False)
    for column in NUTRIENTS.values():
        values = pd.to_numeric(df[column], errors="coerce")
        if column == "calories_kcal":
            df[column] = values.where(values.gt(0) & values.lt(float("inf")))
        else:
            df[column] = values.where(values.ge(0) & values.lt(float("inf"))).fillna(0)
    df["name"] = df["name"].str.strip()
    df["meal_category"] = df["meal_category"].str.strip().str.lower()
    df["diet_type"] = df["diet_type"].map(diet_key)
    return df[df["name"].ne("")].reset_index(drop=True)


def food_to_dict(row):
    nutrients = {
        key: round(float(row[column]), 1) if pd.notna(row[column]) else None
        for key, column in NUTRIENTS.items()
    }
    return {
        "id": int(row.name), "name": row["name"], "category": row["meal_category"],
        "diet": row["diet_type"], "region": row["region"], "serving": row["serving_description"],
        "basis": row["nutrition_basis"], "ingredients": row["ingredients_text"], **nutrients,
    }
