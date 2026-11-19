import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import create_app
from app.recommender import DIETS, MEAL_CATEGORIES


PROFILE = {"age": 25, "height": 165, "weight": 65, "diet": "vegetarian"}


class NutriAITests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        storage = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch("app.auth.USERS_PATH", Path(storage) / "users.json"))

    def login(self):
        account = {"email": "tester@example.com", "password": "test-pass-1"}
        self.assertEqual(self.client.post("/api/signup", json=account).status_code, 200)
        self.assertEqual(self.client.post("/api/login", json=account).status_code, 200)

    def test_health(self):
        self.assertEqual(self.client.get("/api/health").json["dataset_items"], 1331)

    def test_signup_login_logout_and_route_guards(self):
        landing = self.client.get("/")
        self.assertEqual(landing.status_code, 200)
        self.assertIn("Eat colorful.", landing.text)
        self.assertIn("dailyQuote", landing.text)
        paths = ["/dashboard", "/dashboard/week", "/dashboard/nutrition", "/dashboard/foods", "/dashboard/grocery"]
        for path in paths:
            self.assertEqual(self.client.get(path).location, "/welcome")
        self.assertEqual(self.client.get("/api/stats").status_code, 401)
        self.assertEqual(self.client.post("/api/plan", json=PROFILE).status_code, 401)
        self.assertEqual(self.client.post("/api/login", json={"email": "none@example.com", "password": "test"}).status_code, 401)
        self.login()
        self.assertEqual(self.client.get("/").location, "/dashboard")
        for path in paths:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.text.count('aria-current="page"'), 1)
        self.assertEqual(self.client.get("/api/stats").json["foods"], 1331)
        self.assertEqual(self.client.post("/api/logout").status_code, 200)
        self.assertEqual(self.client.get("/api/me").status_code, 401)

    def test_plan_and_swap_preserve_diet_and_slot(self):
        self.login()
        for diet, allowed in DIETS.items():
            with self.subTest(diet=diet):
                profile = {**PROFILE, "diet": diet}
                response = self.client.post("/api/plan", json=profile)
                self.assertEqual(response.status_code, 200, response.json)
                days = response.json["days"]
                self.assertEqual(len(days), 7)
                seen = set()
                for day in days:
                    self.assertEqual({meal["slot"] for meal in day["meals"]}, set(MEAL_CATEGORIES))
                    for meal in day["meals"]:
                        self.assertIn(meal["diet"], allowed)
                        self.assertIn(meal["category"], MEAL_CATEGORIES[meal["slot"]])
                        self.assertNotIn(meal["name"], seen)
                        self.assertGreater(meal["calories"], 0)
                        seen.add(meal["name"])
                for meal in days[0]["meals"]:
                    swapped = self.client.post("/api/swap", json={
                        "profile": profile, "current_name": meal["name"], "slot": meal["slot"],
                        "used_names": list(seen), "seed": 1,
                    })
                    self.assertEqual(swapped.status_code, 200, swapped.json)
                    self.assertEqual(swapped.json["slot"], meal["slot"])
                    self.assertIn(swapped.json["category"], MEAL_CATEGORIES[meal["slot"]])
                    self.assertIn(swapped.json["diet"], allowed)
                    self.assertNotIn(swapped.json["name"], seen)

    def test_catalog_literal_search_filter_and_pagination(self):
        self.login()
        self.assertEqual(self.client.get("/api/search?q=%5B").status_code, 200)
        self.assertEqual(self.client.get("/api/search?q=.%2A").json, [])
        first = self.client.get("/api/search?diet=vegetarian")
        second = self.client.get("/api/search?diet=vegetarian&page=2")
        self.assertGreater(int(first.headers["X-Total-Count"]), len(first.json))
        self.assertTrue({row["id"] for row in first.json}.isdisjoint(row["id"] for row in second.json))
        self.assertTrue(all(row["diet"] in {"vegetarian", "vegan"} for row in first.json))
        dish = self.client.get(f"/api/recipe?id={first.json[0]['id']}")
        self.assertEqual(dish.json["name"], first.json[0]["name"])
        self.assertIsInstance(dish.json["ingredients"], list)

    def test_food_discovery_endpoints(self):
        self.login()
        pantry = self.client.post("/api/pantry", json={"ingredients": ["rice", "tomato"], "diet": "vegetarian"})
        self.assertEqual(pantry.status_code, 200, pantry.json)
        self.assertIn("matches", pantry.json)
        mood = self.client.post("/api/mood", json={"mood": "comfort", "diet": "vegetarian"})
        self.assertEqual(mood.status_code, 200, mood.json)
        self.assertIn("matches", mood.json)
        self.assertEqual(self.client.post("/api/pantry", json={"ingredients": []}).status_code, 400)
        self.assertEqual(self.client.post("/api/mood", json={"mood": "unknown"}).status_code, 400)
        self.assertEqual(self.client.get("/api/substitute?id=0&diet=vegetarian").status_code, 200)
        plan = self.client.post("/api/plan", json=PROFILE).json
        diversity = self.client.post("/api/diversity", json={"plan": plan})
        self.assertEqual(diversity.status_code, 200, diversity.json)
        insights = self.client.post("/api/nutrition-insights", json={"plan": plan})
        self.assertEqual(insights.status_code, 200, insights.json)

    def test_invalid_inputs(self):
        self.login()
        for invalid in ([], {}, {**PROFILE, "age": "nan"}, {**PROFILE, "weight": []},
                        {**PROFILE, "activity": "other"}, {**PROFILE, "diet": "all"}):
            self.assertEqual(self.client.post("/api/plan", json=invalid).status_code, 400)
        self.assertEqual(self.client.post("/api/swap", json={"slot": "other"}).status_code, 400)
        self.assertEqual(self.client.get("/api/recipe").status_code, 400)
