# NutriAI

NutriAI is a local Flask meal planner built around the supplied food catalog.

## Run on Windows

Extract the ZIP, open PowerShell in the folder containing `run.py`, and run:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

Open http://127.0.0.1:5000, create an account, then log in. Use the **Planner** to generate a week, **Weekly plan** to focus on a day, swap meals, view dish details, and print the full week, **Nutrition** to compare daily calories with the estimated target, **Food catalog** to search dishes, view ingredients, and revisit saved favorites, and **Grocery list** to search ingredients, track shopping progress, and show unchecked items.

The first dependency install needs access to Python packages. After installation the app runs locally with the bundled catalog, with no Supabase credentials or external service. Accounts are stored in `users.json` with hashed passwords. An existing `users.json` from the original project can be copied into this folder. Plans, saved dishes, and grocery checkmarks are stored by account in the browser. Generate a fresh plan after upgrading to use the repaired filters. The local session key refreshes on server restart unless the `SECRET_KEY` environment variable is set.

## Dataset and meal selection

The bundled UTF-8 CSV was exported from the **Food Catalog** sheet of `NutriAI_Final_Dataset.xlsx` with all 1,331 rows. The catalog shows both per-serving and per-100-g records. Plan generation uses per-serving records with usable calorie values, so 100-g references are not treated as full meals.

Vegetarian plans include vegetarian and vegan foods. Vegan and non-vegetarian plans use their corresponding workbook labels. Egg-only and unverified diet labels are available in the unfiltered catalog. Each meal and swap stays within the selected diet and slot. Lunch and dinner can use shared lunch/dinner dishes and staples; snacks include beverages and desserts. Selection favors unused dishes near the slot's calorie estimate.

The calculator gives an approximate adult planning target. Nutrition values and ingredient lists come from the workbook. The workbook does not provide verified allergen information.

## Run the automated tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```



## Food Discovery features

The **Food Discovery** page adds dataset-backed tools:

- **Smart Pantry Finder** searches the catalog's `ingredients_text` for ingredients entered by the user. It returns matches and the matched ingredient terms; it does not generate recipes or claim that unlisted ingredients are absent.
- **Food Mood Matcher** filters by transparent keyword and meal-category rules for comfort, spicy, refreshing, quick, or protein-containing preferences. This is a preference tool, not medical or nutrition advice.
- **Similar Dish Substitution** compares only records in the same meal category and diet filter with `per serving (source)` nutrition basis. It ranks by similarity across available calories, protein, carbohydrates, fat and fibre. It does not claim nutritional equivalence.
- **Food Diversity** reports unique dishes, repeated meals, categories and recorded regions in the current weekly plan. Its percentage is the unique-dish share, not a diet-quality score.
- **Personal Preference Feedback** lets a user like or dislike a dish. Ratings are stored in browser local storage, scoped by signed-in email, and influence ordering in Pantry Finder and Mood Matcher. They are not model training and do not sync across devices.
- **Hydration Check-in** is a manual serving counter stored in the browser for the current local date. It deliberately does not prescribe a daily water target.

The existing catalog is the source of ingredient and nutrition values. Allergen information remains unverified where the source dataset says it is unverified; users should check packaging and source recipes independently.

### New API routes

- `POST /api/pantry` — `{ "ingredients": ["rice", "tomato"], "diet": "all", "preferences": {} }`
- `POST /api/mood` — `{ "mood": "comfort", "diet": "all", "preferences": {} }`
- `GET /api/substitute?id=<food_id>&diet=<diet>`
- `POST /api/diversity` — `{ "plan": <generated weekly plan> }`
- `POST /api/nutrition-insights` — `{ "plan": <generated weekly plan> }`

All four routes require a signed-in session, like the existing dashboard APIs.
- **Nutrition Pattern Explorer** totals the dataset's recorded calories, protein, carbohydrates, fat and fibre per day, reports weekly averages and counts missing values. It intentionally does not diagnose deficiencies or prescribe personal nutrient targets.

## Discovery dashboard pages

The former single Food Discovery destination is now split into focused dashboard pages:

- **Pantry Studio** (`/dashboard/pantry`) — find catalog dishes from ingredients on hand.
- **Mood Kitchen** (`/dashboard/mood`) — filter catalog dishes by the selected food mood.
- **Nutrition Lab** (`/dashboard/insights`) — inspect recorded nutrition values in the current weekly plan.
- **Variety Score** (`/dashboard/diversity`) — analyse unique dishes and variety in the current plan.
- **Hydration Hub** (`/dashboard/hydration`) — record water servings for the current day in this browser.

Each destination has its own navigation entry and page, while reusing the existing catalog and feature endpoints. Hydration entries remain browser-local and are not synchronised between devices.
