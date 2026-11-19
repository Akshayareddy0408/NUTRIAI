from flask import Blueprint, current_app, jsonify, render_template, request, session, redirect, url_for

from .auth import authenticate, create_user
from .data_loader import food_to_dict, load_foods
from .recommender import DIETS, MEAL_CATEGORIES, diet_key, filter_diet, recommend_week, swap_meal, validate_profile
from .extra_features import pantry_matches, mood_matches, substitute, diversity_summary, nutrition_insights
from psycopg.types.json import Jsonb
from .db import get_db_connection
bp = Blueprint("main", __name__)
PAGES = {
    "home": "My dashboard", "planner": "Planner", "week": "Weekly plan", "nutrition": "Nutrition",
    "foods": "Food catalog", "grocery": "Grocery list",
    "pantry": "Pantry Studio", "mood": "Mood Kitchen",
    "insights": "Nutrition Lab", "diversity": "Variety Score", "hydration": "Hydration Hub",
}


def foods():
    return load_foods(current_app.config["DATA_PATH"])


def logged_in():
    return bool(session.get("user_email"))


def json_payload():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


@bp.before_request
def protect_dashboard():
    if logged_in():
        return
    if request.endpoint == "main.index":
        return redirect(url_for("main.welcome_page"))
    if request.path.startswith("/api/") and request.endpoint not in {
        "main.health", "main.login", "main.signup", "main.logout",
    }:
        return jsonify(error="Please log in to use NutriAI."), 401


@bp.get("/")
def landing():
    """Public welcome dashboard; never show the login form as the homepage."""
    if logged_in():
        return redirect(url_for("main.index", page="home"))
    return render_template("welcome.html")


@bp.get("/dashboard", defaults={"page": "home"})
@bp.get("/dashboard/<any(home,planner,week,nutrition,foods,grocery,pantry,mood,insights,diversity,hydration):page>")
def index(page):
    return render_template("index.html", page=page, pages=PAGES, email=session["user_email"])


@bp.get("/welcome")
def welcome_page():
    if logged_in():
        return redirect(url_for("main.index", page="home"))
    return render_template("welcome.html")


@bp.get("/login")
def login_page():
    if logged_in():
        return redirect(url_for("main.index", page="home"))
    return render_template("auth.html", mode="login")


@bp.get("/signup")
def signup_page():
    if logged_in():
        return redirect(url_for("main.index", page="home"))
    return render_template("auth.html", mode="signup")


@bp.post("/api/signup")
def signup():
    data = json_payload()
    email, password = data.get("email"), data.get("password")
    if not isinstance(email, str) or not isinstance(password, str):
        return jsonify(error="Enter an email and password."), 400
    try:
        ok, message = create_user(email, password)
    except Exception:
        current_app.logger.exception("Signup could not reach the database")
        return jsonify(error="Could not save the account to Supabase. Check the database connection and run the supplied schema SQL."), 503
    return jsonify(message=message) if ok else (jsonify(error=message), 400)


@bp.post("/api/login")
def login():
    data = json_payload()
    email, password = data.get("email"), data.get("password")
    if not isinstance(email, str) or not isinstance(password, str):
        return jsonify(error="Incorrect email or password."), 401
    try:
        authenticated = authenticate(email, password)
    except Exception:
        current_app.logger.exception("Login could not reach the database")
        return jsonify(error="Could not check your account in Supabase. Check the database connection and run the supplied schema SQL."), 503
    if not authenticated:
        return jsonify(error="Incorrect email or password."), 401
    session.clear()
    session["user_email"] = email.strip().lower()
    return jsonify(message="Login successful.")


@bp.post("/api/logout")
def logout():
    session.clear()
    return jsonify(message="Logged out.")


@bp.get("/api/me")
def me():
    return jsonify(logged_in=True, email=session["user_email"])


@bp.get("/api/health")
def health():
    return jsonify(status="ok", message="NutriAI is running", dataset_items=len(foods()))


@bp.get("/api/stats")
def stats():
    df = foods()
    return jsonify(
        foods=len(df), categories=sorted(df["meal_category"].unique()),
        diets=sorted(df["diet_type"].unique()),
        regions=sorted(value for value in df["region"].unique() if value.strip()),
    )


@bp.post("/api/plan")
def plan():
    try:
        profile = validate_profile(json_payload())
        return jsonify(recommend_week(foods(), profile))
    except ValueError as error:
        return jsonify(error=str(error)), 400


@bp.post("/api/swap")
def swap():
    data = json_payload()
    slot, name = data.get("slot"), data.get("current_name")
    used_names = data.get("used_names", [])
    seed = data.get("seed")
    if (not isinstance(slot, str) or slot not in MEAL_CATEGORIES or
        not isinstance(name, str) or not name.strip() or
        not isinstance(used_names, list) or len(used_names) > 28 or
        any(not isinstance(item, str) for item in used_names) or
        (seed is not None and not isinstance(seed, (int, str)))):
        return jsonify(error="Select a valid meal to swap."), 400
    try:
        profile = validate_profile(data.get("profile"))
    except ValueError as error:
        return jsonify(error=str(error)), 400
    result = swap_meal(foods(), name, slot, profile, seed, used_names)
    if result is None:
        return jsonify(error="No alternative found for this meal and diet."), 404
    return jsonify(result)


@bp.get("/api/search")
def search():
    query = request.args.get("q", "").strip().casefold()
    diet = diet_key(request.args.get("diet", "all")) or "all"
    if diet not in DIETS and diet not in {"all", "egg", "unclear---verify"}:
        return jsonify(error="Choose a valid catalog diet."), 400
    page = request.args.get("page", 1, type=int)
    if page < 1:
        return jsonify(error="Choose a valid page."), 400
    df = filter_diet(foods(), diet)
    if query:
        df = df[df["name"].str.casefold().str.contains(query, regex=False)]
    limit = 30
    offset = (page - 1) * limit
    response = jsonify([food_to_dict(row) for _, row in df.iloc[offset:offset + limit].iterrows()])
    response.headers["X-Total-Count"] = str(len(df))
    return response


@bp.get("/api/recipe")
def recipe():
    df = foods()
    name = request.args.get("name", "").strip().casefold()
    food_id = request.args.get("id", type=int)
    if food_id is not None:
        hit = df.loc[df.index == food_id]
    elif name:
        hit = df[df["name"].str.casefold() == name]
    else:
        return jsonify(error="Select a dish."), 400
    if hit.empty:
        return jsonify(error="Dish not found."), 404
    dish = food_to_dict(hit.iloc[0])
    dish["ingredients"] = [item.strip() for item in dish["ingredients"].split(";") if item.strip()]
    return jsonify(dish)


@bp.post("/api/pantry")
def pantry():
    data = json_payload()
    try:
        return jsonify(pantry_matches(foods(), data.get("ingredients"), data.get("diet", "all"), data.get("preferences")))
    except ValueError as error:
        return jsonify(error=str(error)), 400


@bp.post("/api/mood")
def mood():
    data = json_payload()
    try:
        return jsonify(mood_matches(foods(), data.get("mood"), data.get("diet", "all"), data.get("preferences")))
    except ValueError as error:
        return jsonify(error=str(error)), 400


@bp.get("/api/substitute")
def food_substitute():
    try:
        food_id = request.args.get("id", type=int)
        if food_id is None:
            raise ValueError("Choose a dish to compare.")
        return jsonify(substitute(foods(), food_id, request.args.get("diet", "all")))
    except ValueError as error:
        return jsonify(error=str(error)), 400


@bp.post("/api/diversity")
def diversity():
    try:
        return jsonify(diversity_summary(json_payload().get("plan")))
    except ValueError as error:
        return jsonify(error=str(error)), 400


@bp.post("/api/nutrition-insights")
def nutrition_pattern():
    try:
        return jsonify(nutrition_insights(json_payload().get("plan")))
    except ValueError as error:
        return jsonify(error=str(error)), 400

@bp.post("/api/save-plan")
def save_plan():
    data = json_payload()
    plan_data = data.get("plan")
    profile_data = data.get("profile", {})

    if not isinstance(plan_data, dict) or not isinstance(plan_data.get("days"), list):
        return jsonify(error="Invalid meal plan."), 400

    email = session["user_email"]

    try:
        with get_db_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO public.meal_plans
                (user_email, plan_name, plan_data, profile_data)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                (
                    email,
                    "My Weekly Meal Plan",
                    Jsonb(plan_data),
                    Jsonb(profile_data)
                )
            )

            plan_id = cursor.fetchone()["id"]

            for day in plan_data["days"]:
                for meal in day.get("meals", []):
                    conn.execute(
                        """
                        INSERT INTO public.meal_plan_items
                        (
                            meal_plan_id, user_email, day_number,
                            meal_category, food_name, calories,
                            protein, carbohydrates, fat, food_data
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            plan_id,
                            email,
                            day.get("day"),
                            meal.get("slot", "Meal"),
                            meal.get("name", "Unknown"),
                            meal.get("calories"),
                            meal.get("protein"),
                            meal.get("carbs"),
                            meal.get("fat"),
                            Jsonb(meal)
                        )
                    )

        return jsonify(message="Plan saved!", plan_id=plan_id)

    except Exception:
        current_app.logger.exception("Could not save meal plan")
        return jsonify(error="Could not save meal plan."), 500

@bp.post("/api/hydration/sync")
def sync_hydration():
    data = json_payload()
    email = session["user_email"]

    log = data.get("log", [])
    pet = data.get("pet", {})

    if not isinstance(log, list) or not isinstance(pet, dict):
        return jsonify(error="Invalid hydration data."), 400

    try:
        from datetime import date
        from psycopg.types.json import Jsonb

        today = date.today()

        with get_db_connection() as conn:
            conn.execute(
                """
                DELETE FROM public.hydration_entries
                WHERE user_email = %s AND local_date = %s
                """,
                (email, today)
            )

            for entry in log[-99:]:
                amount = int(entry.get("ml", 0))
                if amount <= 0:
                    continue

                conn.execute(
                    """
                    INSERT INTO public.hydration_entries
                    (user_email, amount_ml, local_date, display_time)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (email, amount, today, str(entry.get("time", "")))
                )

            pet_values = (
                int(pet.get("xp", 0)),
                int(pet.get("goal", 2000)),
                Jsonb(pet.get("badges", [])),
                email,
            )
            updated = conn.execute(
                """
                UPDATE public.hydration_pet_state
                SET xp = %s, daily_goal_ml = %s, badges = %s, updated_at = NOW()
                WHERE user_email = %s
                """,
                pet_values
            )
            if updated.rowcount == 0:
                conn.execute(
                    """
                    INSERT INTO public.hydration_pet_state
                    (user_email, xp, daily_goal_ml, badges, updated_at)
                    VALUES (%s, %s, %s, %s, NOW())
                    """,
                    (email, *pet_values[:3])
                )

        return jsonify(message="Hydration saved successfully.")

    except Exception:
        current_app.logger.exception("Hydration sync failed")
        return jsonify(error="Could not save hydration data."), 500

@bp.get("/api/data")
def load_saved_data():
    email = session["user_email"]

    try:
        with get_db_connection() as conn:
            grocery = conn.execute(
                """
                SELECT id, item_name, quantity, is_purchased
                FROM public.grocery_items
                WHERE user_email = %s
                ORDER BY id
                """, (email,)
            ).fetchall()

            pantry = conn.execute(
                """
                SELECT id, item_name, quantity
                FROM public.pantry_items
                WHERE user_email = %s
                ORDER BY id
                """, (email,)
            ).fetchall()

            recipes = conn.execute(
                """
                SELECT id, recipe_name, recipe_data
                FROM public.saved_recipes
                WHERE user_email = %s
                ORDER BY id DESC
                """, (email,)
            ).fetchall()

            preferences = conn.execute(
                """
                SELECT preferences
                FROM public.user_preferences
                WHERE user_email = %s
                """, (email,)
            ).fetchone()

            latest_plan = conn.execute(
                """
                SELECT id, plan_data, profile_data
                FROM public.meal_plans
                WHERE user_email = %s
                ORDER BY created_at DESC
                LIMIT 1
                """, (email,)
            ).fetchone()

            from datetime import date
            hydration = conn.execute(
                """
                SELECT id, amount_ml, local_date, display_time
                FROM public.hydration_entries
                WHERE user_email = %s AND local_date = %s
                ORDER BY id
                """,
                (email, date.today())
            ).fetchall()

            hydration_pet = conn.execute(
                """
                SELECT xp, daily_goal_ml, badges
                FROM public.hydration_pet_state
                WHERE user_email = %s
                """,
                (email,)
            ).fetchone()

        return jsonify(
            grocery=grocery,
            pantry=pantry,
            recipes=recipes,
            preferences=preferences["preferences"] if preferences else {},
            latest_plan=latest_plan,
            hydration=hydration,
            hydration_pet=hydration_pet
        )

    except Exception:
        current_app.logger.exception("Could not load saved data")
        return jsonify(error="Could not load saved data."), 500


@bp.post("/api/grocery/sync")
def sync_grocery():
    data = json_payload()
    items = data.get("items", [])

    if not isinstance(items, list):
        return jsonify(error="Invalid grocery items."), 400

    email = session["user_email"]

    try:
        with get_db_connection() as conn:
            conn.execute(
                "DELETE FROM public.grocery_items WHERE user_email = %s",
                (email,)
            )

            for item in items:
                if not isinstance(item, dict):
                    continue

                name = str(item.get("name", "")).strip()
                if not name:
                    continue

                conn.execute(
                    """
                    INSERT INTO public.grocery_items
                    (user_email, item_name, quantity, is_purchased)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        email,
                        name,
                        str(item.get("quantity", "1")),
                        bool(item.get("purchased", False))
                    )
                )

        return jsonify(message="Grocery list saved.")

    except Exception:
        current_app.logger.exception("Grocery sync failed")
        return jsonify(error="Could not save grocery list."), 500


@bp.post("/api/pantry/save")
def save_pantry():
    data = json_payload()
    items = data.get("items", [])

    if not isinstance(items, list):
        return jsonify(error="Invalid pantry items."), 400

    email = session["user_email"]

    try:
        with get_db_connection() as conn:
            conn.execute(
                "DELETE FROM public.pantry_items WHERE user_email = %s",
                (email,)
            )

            for item in items:
                if not isinstance(item, dict):
                    continue

                name = str(item.get("name", "")).strip()
                if not name:
                    continue

                conn.execute(
                    """
                    INSERT INTO public.pantry_items
                    (user_email, item_name, quantity)
                    VALUES (%s, %s, %s)
                    """,
                    (email, name, str(item.get("quantity", "1")))
                )

        return jsonify(message="Pantry saved.")

    except Exception:
        current_app.logger.exception("Pantry save failed")
        return jsonify(error="Could not save pantry."), 500


@bp.post("/api/mood/save")
def save_mood():
    data = json_payload()
    mood = data.get("mood")
    preferences = data.get("preferences", {})

    if not isinstance(mood, str) or not mood.strip():
        return jsonify(error="Choose a mood."), 400

    if not isinstance(preferences, dict):
        return jsonify(error="Invalid preferences."), 400

    try:
        with get_db_connection() as conn:
            conn.execute(
                """
                INSERT INTO public.mood_logs
                (user_email, mood, preferences)
                VALUES (%s, %s, %s)
                """,
                (
                    session["user_email"],
                    mood.strip(),
                    Jsonb(preferences)
                )
            )

        return jsonify(message="Mood saved.")

    except Exception:
        current_app.logger.exception("Mood save failed")
        return jsonify(error="Could not save mood."), 500


@bp.post("/api/recipes/save")
def save_recipe():
    data = json_payload()
    recipe = data.get("recipe")

    if not isinstance(recipe, dict) or not recipe.get("name"):
        return jsonify(error="Invalid recipe."), 400

    email = session["user_email"]
    name = str(recipe["name"]).strip()

    try:
        with get_db_connection() as conn:
            conn.execute(
                """
                DELETE FROM public.saved_recipes
                WHERE user_email = %s AND recipe_name = %s
                """,
                (email, name)
            )
            conn.execute(
                """
                INSERT INTO public.saved_recipes
                (user_email, recipe_name, recipe_data)
                VALUES (%s, %s, %s)
                """,
                (email, name, Jsonb(recipe))
            )

        return jsonify(message="Recipe saved.")

    except Exception:
        current_app.logger.exception("Recipe save failed")
        return jsonify(error="Could not save recipe."), 500


@bp.get("/api/recipes")
def list_saved_recipes():
    try:
        with get_db_connection() as conn:
            recipes = conn.execute(
                """
                SELECT id, recipe_name, recipe_data
                FROM public.saved_recipes
                WHERE user_email = %s
                ORDER BY id DESC
                """,
                (session["user_email"],)
            ).fetchall()
        return jsonify(recipes=recipes)
    except Exception:
        current_app.logger.exception("Could not load saved recipes")
        return jsonify(error="Could not load saved recipes from Supabase."), 500


@bp.post("/api/recipes/delete")
def delete_recipe():
    data = json_payload()
    name = data.get("name")

    if not isinstance(name, str) or not name.strip():
        return jsonify(error="Invalid recipe name."), 400

    try:
        with get_db_connection() as conn:
            conn.execute(
                """
                DELETE FROM public.saved_recipes
                WHERE user_email = %s AND recipe_name = %s
                """,
                (session["user_email"], name.strip())
            )

        return jsonify(message="Recipe removed.")

    except Exception:
        current_app.logger.exception("Recipe delete failed")
        return jsonify(error="Could not remove recipe."), 500


@bp.post("/api/preferences/save")
def save_preferences():
    data = json_payload()
    preferences = data.get("preferences", {})

    if not isinstance(preferences, dict):
        return jsonify(error="Invalid preferences."), 400

    try:
        with get_db_connection() as conn:
            conn.execute(
                """
                DELETE FROM public.user_preferences
                WHERE user_email = %s
                """,
                (session["user_email"],)
            )
            conn.execute(
                """
                INSERT INTO public.user_preferences
                (user_email, preferences, updated_at)
                VALUES (%s, %s, NOW())
                """,
                (session["user_email"], Jsonb(preferences))
            )

        return jsonify(message="Preferences saved.")

    except Exception:
        current_app.logger.exception("Preferences save failed")
        return jsonify(error="Could not save preferences."), 500


@bp.post("/api/food-log")
def save_food_log():
    data = json_payload()
    name = data.get("food_name")
    quantity = data.get("quantity", "1")
    nutrition = data.get("nutrition_data", {})

    if not isinstance(name, str) or not name.strip():
        return jsonify(error="Enter a food name."), 400

    if not isinstance(nutrition, dict):
        return jsonify(error="Invalid nutrition data."), 400

    try:
        with get_db_connection() as conn:
            conn.execute(
                """
                INSERT INTO public.food_logs
                (user_email, food_name, quantity, nutrition_data)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    session["user_email"],
                    name.strip(),
                    str(quantity),
                    Jsonb(nutrition)
                )
            )

        return jsonify(message="Food log saved.")

    except Exception:
        current_app.logger.exception("Food log save failed")
        return jsonify(error="Could not save food log."), 500


@bp.post("/api/nutrition-history")
def save_nutrition_history():
    data = json_payload()
    nutrition = data.get("nutrition_data")

    if not isinstance(nutrition, dict):
        return jsonify(error="Invalid nutrition data."), 400

    try:
        with get_db_connection() as conn:
            conn.execute(
                """
                INSERT INTO public.nutrition_history
                (user_email, nutrition_data)
                VALUES (%s, %s)
                """,
                (session["user_email"], Jsonb(nutrition))
            )

        return jsonify(message="Nutrition history saved.")

    except Exception:
        current_app.logger.exception("Nutrition history save failed")
        return jsonify(error="Could not save nutrition history."), 500
