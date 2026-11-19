
const $ = (selector) => document.querySelector(selector);
const { page, account, weekUrl } = document.body.dataset;
const key = `nutriai:v2:${account}`;
const number = new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 });

const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (character) => ({
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
})[character]);

const total = (meals, field) =>
  meals.reduce((sum, meal) => sum + (Number(meal[field]) || 0), 0);

const mealsOf = (plan) => plan.days.flatMap((day) => day.meals);

function readState() {
  try {
    const saved = JSON.parse(localStorage.getItem(key));
    if (saved && typeof saved === "object" && !Array.isArray(saved)) return saved;
  } catch {
    return {};
  }
  return {};
}

let state = readState();
let statusTimer;

function notify(message) {
  const status = $("#status");
  if (!status) return;

  status.textContent = message;
  status.hidden = false;

  clearTimeout(statusTimer);
  statusTimer = setTimeout(() => {
    status.hidden = true;
  }, 6500);
}

function saveState(next) {
  localStorage.setItem(key, JSON.stringify(next));
  state = next;
}

async function api(path, data) {
  const options = data === undefined ? {} : {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  };

  const response = await fetch(path, options);

  if (response.status === 401) {
    location.assign("/login");
    throw new Error("Please log in again.");
  }

  const responseText = await response.text();
  let result;
  try {
    result = responseText ? JSON.parse(responseText) : {};
  } catch {
    const detail = response.status === 404
      ? `NutriAI route ${path} was not found (HTTP 404). Restart the app from the NutriAI project folder.`
      : `The server returned an unexpected response (HTTP ${response.status}). Check the Flask terminal.`;
    throw new Error(detail);
  }

  if (!response.ok) {
    throw new Error(result.error || "The request could not be completed.");
  }

  return { result, response };
}

function bindAction(button, action) {
  button.addEventListener("click", async () => {
    button.disabled = true;

    try {
      await action();
    } catch (error) {
      notify(error.message);
    } finally {
      button.disabled = false;
    }
  });
}

document.querySelectorAll("#logout, .logout-action").forEach((button) => {
  bindAction(button, async () => {
    await api("/api/logout", {});
    location.assign("/");
  });
});

// --------------------------------------------------
// MEAL PLAN GENERATION AND SUPABASE SAVING
// --------------------------------------------------

async function generate(profile) {
  const { result: plan } = await api("/api/plan", profile);

  await api("/api/save-plan", {
    plan,
    profile
  });

  saveState({
    ...state,
    profile,
    plan,
    checked: []
  });
}

// --------------------------------------------------
// HOME PAGE
// --------------------------------------------------

function home() {
  const displayName =
    state.profile?.name?.trim() ||
    account.split("@")[0]
      .replace(/[._-]+/g, " ")
      .replace(/\b\w/g, (c) => c.toUpperCase()) ||
    "friend";

  $("#welcomeName").textContent = displayName.split(/\s+/)[0];

  const quotes = [
    "Take care of your body. It's the only place you have to live.",
    "A healthy outside starts from the inside.",
    "Progress is made one small, kind choice at a time.",
    "Nourish your body. Feed your joy. Be kind to yourself.",
    "You don't have to be perfect to make a positive change."
  ];

  const today = new Date();

  const dateKey = (date) =>
    `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;

  const todayKey = dateKey(today);

  const dates = Array.isArray(state.wellnessDates)
    ? state.wellnessDates.filter((d) => /^\d{4}-\d{2}-\d{2}$/.test(d))
    : [];

  if (!dates.includes(todayKey)) dates.push(todayKey);

  const sorted = [...new Set(dates)].sort().slice(-90);

  saveState({ ...state, wellnessDates: sorted });

  const dayBefore = (key) => {
    const d = new Date(`${key}T12:00:00`);
    d.setDate(d.getDate() - 1);
    return dateKey(d);
  };

  let streak = 0;
  let cursor = todayKey;
  const active = new Set(sorted);

  while (active.has(cursor)) {
    streak++;
    cursor = dayBefore(cursor);
  }

  $("#streakCount").textContent = streak;

  $("#streakMessage").textContent =
    streak >= 7
      ? "A whole week of showing up for yourself. That's worth celebrating!"
      : "You showed up for yourself today. Keep it gentle and keep it going.";

  $("#streakDots").innerHTML = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(today);
    d.setDate(d.getDate() - (6 - i));
    const k = dateKey(d);

    return `<span class="streak-day ${active.has(k) ? "done" : ""}" title="${k}">${["S", "M", "T", "W", "T", "F", "S"][d.getDay()]}</span>`;
  }).join("");

  const quoteIndex = Math.floor(
    (today.getFullYear() * 372 + (today.getMonth() + 1) * 31 + today.getDate()) % quotes.length
  );

  $("#dailyQuote").textContent = `“${quotes[quoteIndex]}”`;

  const hydrationKey = `nutriai:water-log:${account}:${todayKey}`;
  let water = [];

  try {
    const saved = JSON.parse(localStorage.getItem(hydrationKey) || "[]");
    if (Array.isArray(saved)) water = saved;
  } catch {
    water = [];
  }

  $("#homeWater").textContent =
    `${water.length} serving${water.length === 1 ? "" : "s"}`;

  if (!state.plan) return;

  const meals = mealsOf(state.plan);

  const average = (field) =>
    meals.reduce((sum, m) => sum + (Number(m[field]) || 0), 0) /
    Math.max(1, state.plan.days.length);

  const calories = average("calories");
  const protein = average("protein");
  const unique = new Set(meals.map((m) => m.name)).size;

  $("#homeMeals").textContent = `${meals.length} meals ready`;
  $("#homeCalories").textContent = `${number.format(calories)} kcal`;

  $("#homeCaloriesHint").textContent =
    `Daily plan target: ${number.format(state.plan.target_calories)} kcal`;

  $("#homeVariety").textContent = `${unique} dishes`;

  const target = Number(state.plan.target_calories) || calories || 1;
  const caloriePct = Math.min(100, Math.round(calories / target * 100));
  const days = state.plan.days.length;

  $("#homeProgress").innerHTML = `
    <div class="progress-line">
      <div><strong>Weekly meal plan</strong><span>${days} of 7 days planned</span></div>
      <div class="progress-track"><i style="width:${Math.min(100, days / 7 * 100)}%"></i></div>
    </div>
    <div class="progress-line">
      <div><strong>Average daily calories</strong><span>${number.format(calories)} / ${number.format(target)} kcal</span></div>
      <div class="progress-track peach-track"><i style="width:${caloriePct}%"></i></div>
    </div>
    <div class="progress-line">
      <div><strong>Average protein</strong><span>${number.format(protein)} g per day · based on your plan</span></div>
      <div class="progress-track mint-track"><i style="width:${Math.min(100, protein / 100 * 100)}%"></i></div>
    </div>
    <p class="progress-note">These are summaries of your generated meal plan, not medical targets. Your needs may differ.</p>`;
}

// --------------------------------------------------
// PLANNER PAGE
// --------------------------------------------------

function planner() {
  const form = $("#profileForm");

  if (state.profile) {
    for (const [key, value] of Object.entries(state.profile)) {
      const field = form.elements.namedItem(key);
      if (field) field.value = value;
    }
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();

    const button = form.querySelector("button");
    button.disabled = true;

    notify("Building your meal plan…");

    try {
      await generate(Object.fromEntries(new FormData(form)));
      location.assign(weekUrl);
    } catch (error) {
      notify(error.message);
    } finally {
      button.disabled = false;
    }
  });
}

// --------------------------------------------------
// WEEKLY PLAN
// --------------------------------------------------

function renderWeek() {
  $("#weekGrid").innerHTML = state.plan.days.map((day, dayIndex) => `
    <article class="day-card" data-plan-day="${day.day}">
      <header class="day-head">
        <h2>Day ${day.day}</h2>
        <span>${number.format(total(day.meals, "calories"))} kcal</span>
      </header>
      ${day.meals.map((meal, mealIndex) => `
        <div class="meal">
          <div>
            <span class="slot">${escapeHtml(meal.slot)}</span>
            <h3>
              <button class="meal-details" type="button"
                data-details="${mealIndex}" data-day="${dayIndex}"
                aria-label="View ${escapeHtml(meal.name)} details">
                ${escapeHtml(meal.name)}
              </button>
            </h3>
            <span class="muted">
              ${number.format(meal.calories)} kcal · ${number.format(meal.protein)} g protein
            </span>
          </div>
          <button class="btn" data-day="${dayIndex}" data-meal="${mealIndex}"
            aria-label="Swap day ${day.day} ${escapeHtml(meal.slot)}">
            Swap
          </button>
        </div>`).join("")}
    </article>`).join("");
}

function week() {
  renderWeek();

  const regenerate = $("#regenerate");
  const grid = $("#weekGrid");
  const picker = $("#dayPicker");

  $("#weekActions").hidden = false;
  picker.hidden = false;

  let selectedDay = "all";
  let busy = false;

  function showSelectedDay() {
    for (const card of grid.querySelectorAll("[data-plan-day]")) {
      card.classList.toggle(
        "day-filtered",
        selectedDay !== "all" && selectedDay !== card.dataset.planDay
      );
    }

    grid.classList.toggle("single-day", selectedDay !== "all");
  }

  picker.addEventListener("click", (event) => {
    const button = event.target.closest("[data-show-day]");
    if (!button) return;

    selectedDay = button.dataset.showDay;

    for (const option of picker.querySelectorAll("button")) {
      option.setAttribute("aria-pressed", option === button);
    }

    showSelectedDay();
  });

  $("#printPlan").addEventListener("click", () => window.print());

  async function update(action) {
    if (busy) return;

    busy = true;
    regenerate.disabled = true;

    grid.querySelectorAll("button").forEach((button) => {
      button.disabled = true;
    });

    try {
      await action();
      renderWeek();
      showSelectedDay();
    } finally {
      busy = false;
      regenerate.disabled = false;

      grid.querySelectorAll("button").forEach((button) => {
        button.disabled = false;
      });
    }
  }

  bindAction(regenerate, () => update(async () => {
    await generate(state.profile);
    notify("Your new weekly plan is ready.");
  }));

  grid.addEventListener("click", async (event) => {
    const details = event.target.closest("button[data-details]");

    if (details) {
      const dish = state.plan.days[details.dataset.day].meals[details.dataset.details];

      details.disabled = true;

      try {
        await showDish(
          dish.id === undefined ? { name: dish.name } : { id: dish.id }
        );
      } catch (error) {
        notify(error.message);
      } finally {
        details.disabled = false;
      }

      return;
    }

    const button = event.target.closest("button[data-meal]");
    if (!button) return;

    const { day, meal } = button.dataset;

    try {
      await update(async () => {
        const plan = structuredClone(state.plan);
        const current = plan.days[day].meals[meal];

        const { result } = await api("/api/swap", {
          current_name: current.name,
          slot: current.slot,
          profile: state.profile,
          used_names: mealsOf(plan).map((item) => item.name),
        });

        plan.days[day].meals[meal] = result;

        await api("/api/save-plan", {
          plan,
          profile: state.profile
        });

        saveState({ ...state, plan });

        notify("Meal swapped and saved.");
      });

      grid.querySelector(
        `[data-day="${day}"][data-meal="${meal}"]`
      )?.focus();

    } catch (error) {
      notify(error.message);
    }
  });
}

// --------------------------------------------------
// NUTRITION PAGE
// --------------------------------------------------

function nutrition() {
  const { plan } = state;
  const meals = mealsOf(plan);
  const daily = plan.days.map((day) => total(day.meals, "calories"));

  const average = (field) =>
    number.format(total(meals, field) / plan.days.length);

  $("#nutritionContent").hidden = false;

  $("#nutritionMetrics").innerHTML = [
    ["Planned daily average", `${average("calories")} kcal`],
    ["Daily protein average", `${average("protein")} g`],
    ["Daily fibre average", `${average("fibre")} g`],
  ].map(([label, value]) => `
    <div class="metric">
      <span class="muted">${label}</span>
      <b>${value}</b>
    </div>`).join("");

  $("#chartLegend").textContent =
    `The line marks your estimated target of ${number.format(plan.target_calories)} kcal/day.`;

  const maximum = Math.max(...daily, plan.target_calories) * 1.08;

  $("#chart").innerHTML = daily.map((value, index) => `
    <div class="bar-row">
      <span>Day ${index + 1}</span>
      <div class="track" aria-hidden="true">
        <div class="bar" style="width:${100 * value / maximum}%"></div>
        <div class="marker" style="left:${100 * plan.target_calories / maximum}%"></div>
      </div>
      <b>${number.format(value)} kcal</b>
    </div>`).join("");
}

// --------------------------------------------------
// FOOD CATALOG AND RECIPES
// --------------------------------------------------

const dietLabel = (diet) => ({
  "vegetarian": "Vegetarian",
  "vegan": "Vegan",
  "non-vegetarian": "Non-vegetarian",
  "egg": "Egg",
  "unclear---verify": "Diet unverified",
})[diet] || "Diet unverified";

const basisLabel = (dish) =>
  dish.basis.startsWith("per 100 g") ? "per 100 g" : "per serving";

const caloriesLabel = (dish) =>
  dish.calories === null
    ? "Calories unavailable"
    : `${number.format(dish.calories)} kcal ${basisLabel(dish)}`;

const favorites = () => state.favorites || [];

async function showDish(lookup) {
  const { result: dish } = await api(
    `/api/recipe?${new URLSearchParams(lookup)}`
  );

  $("#dishDetails").innerHTML = `
    <span class="tag">${escapeHtml(dietLabel(dish.diet))}</span>
    <h2 id="dishTitle">${escapeHtml(dish.name)}</h2>
    <p>
      ${caloriesLabel(dish)} · ${number.format(dish.protein)} g protein ·
      ${number.format(dish.carbs)} g carbs · ${number.format(dish.fat)} g fat
    </p>
    ${dish.serving ? `<p class="muted">${escapeHtml(dish.serving)}</p>` : ""}
    <h3>Ingredients</h3>
    ${dish.ingredients.length
      ? `<ul>${dish.ingredients.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
      : "<p>Ingredients are unavailable.</p>"}
    <p class="muted">Allergen information is unverified.</p>
    <button id="favoriteDish" class="btn favorite-button" type="button" aria-pressed="false">
      Save dish
    </button>`;

  const button = $("#favoriteDish");

  function refreshFavorite() {
    const saved = favorites().some((item) => item.id === dish.id);

    button.setAttribute("aria-pressed", saved);
    button.textContent = saved ? "★ Saved dish" : "☆ Save dish";
  }

  refreshFavorite();

  bindAction(button, async () => {
    const saved = favorites().some((item) => item.id === dish.id);

    if (saved) {
      await api("/api/recipes/delete", {
        name: dish.name
      });
    } else {
      await api("/api/recipes/save", {
        recipe: dish
      });
    }

    const next = saved
      ? favorites().filter((item) => item.id !== dish.id)
      : [...favorites(), dish];

    saveState({ ...state, favorites: next });
    refreshFavorite();
  });

  $("#dish").showModal();
}

// Add preference, substitute and food-log controls to dish details.
const originalShowDish = showDish;

showDish = async function (lookup) {
  await originalShowDish(lookup);

  const { result: dish } = await api(
    `/api/recipe?${new URLSearchParams(lookup)}`
  );

  const details = $("#dishDetails");
  const feedback = state.foodFeedback || {};
  const current = feedback[dish.id] || "";

  const controls = document.createElement("section");
  controls.className = "preference-feedback";

  controls.innerHTML = `
    <h3>Personal preference</h3>
    <p class="muted">Your ratings are saved for this account.</p>
    <button class="btn" type="button" data-rating="like">♡ Like</button>
    <button class="btn" type="button" data-rating="dislike">Not for me</button>
    <span class="muted" aria-live="polite">
      ${current ? `Saved: ${escapeHtml(current)}` : "Not rated"}
    </span>`;

  controls.addEventListener("click", async (event) => {
    const ratingButton = event.target.closest("[data-rating]");
    if (!ratingButton) return;

    ratingButton.disabled = true;

    try {
      const next = {
        ...(state.foodFeedback || {}),
        [dish.id]: ratingButton.dataset.rating
      };

      await api("/api/preferences/save", {
        preferences: next
      });

      saveState({ ...state, foodFeedback: next });

      controls.querySelector("span").textContent =
        `Saved: ${ratingButton.dataset.rating}`;

    } catch (error) {
      notify(error.message);
    } finally {
      ratingButton.disabled = false;
    }
  });

  details.append(controls);

  const substituteButton = document.createElement("button");
  substituteButton.className = "btn";
  substituteButton.type = "button";
  substituteButton.textContent = "Find similar alternatives";

  const resultArea = document.createElement("div");
  resultArea.className = "substitute-results";

  substituteButton.addEventListener("click", async () => {
    substituteButton.disabled = true;

    try {
      const { result } = await api(
        `/api/substitute?id=${encodeURIComponent(dish.id)}&diet=${encodeURIComponent(state.profile?.diet || "all")}`
      );

      resultArea.innerHTML = result.alternatives.length
        ? `
          <h3>Similar catalog dishes</h3>
          ${result.alternatives.map((item) => `
            <p>
              <strong>${escapeHtml(item.name)}</strong> ·
              ${item.calories == null ? "Nutrition unavailable" : `${number.format(item.calories)} kcal`} ·
              ${number.format(item.protein)} g protein
            </p>`).join("")}
          <p class="muted">${escapeHtml(result.note)}</p>`
        : `<p class="muted">${escapeHtml(result.note)}</p>`;

    } catch (error) {
      resultArea.textContent = error.message;
    } finally {
      substituteButton.disabled = false;
    }
  });

  details.append(substituteButton, resultArea);

  const logFoodButton = document.createElement("button");
  logFoodButton.className = "btn";
  logFoodButton.type = "button";
  logFoodButton.textContent = "Log as consumed";

  bindAction(logFoodButton, async () => {
    await api("/api/food-log", {
      food_name: dish.name,
      quantity: "1 serving",
      nutrition_data: {
        calories: dish.calories,
        protein: dish.protein,
        carbohydrates: dish.carbs,
        fat: dish.fat
      }
    });

    notify("Food consumption saved.");
  });

  details.append(logFoodButton);
};

// --------------------------------------------------
// FOOD CATALOG PAGE
// --------------------------------------------------

function catalog() {
  const form = $("#catalogForm");
  const grid = $("#catalog");
  const status = $("#catalogStatus");
  const pagination = $("#pagination");

  let currentPage = 1;
  let filters = new URLSearchParams(new FormData(form));
  let latestRequest = 0;
  let savedOnly = false;

  const all = $("#allDishes");
  const saved = $("#savedDishes");

  function renderCards(dishes) {
    grid.innerHTML = dishes.map((dish) => `
      <article class="food-card animated-food-card">
        <h2>${escapeHtml(dish.name)}</h2>
        <span class="tag ${escapeHtml(dish.diet)}">
          ${escapeHtml(dietLabel(dish.diet))}
        </span>
        <p class="muted">${caloriesLabel(dish)}</p>
        <button class="btn" data-food-id="${dish.id}">View details</button>
      </article>`).join("");
  }

  function renderSaved() {
    const dishes = [...favorites()].sort(
      (first, second) => first.name.localeCompare(second.name)
    );

    status.textContent = dishes.length
      ? `${number.format(dishes.length)} saved ${dishes.length === 1 ? "dish" : "dishes"}`
      : "Open any dish and choose Save dish to add it here.";

    pagination.hidden = true;
    renderCards(dishes);
  }

  function changeView(next) {
    savedOnly = next;

    all.setAttribute("aria-pressed", !next);
    saved.setAttribute("aria-pressed", next);
    form.hidden = next;

    if (next) {
      latestRequest += 1;
      renderSaved();
    } else {
      load(1);
    }
  }

  all.addEventListener("click", () => changeView(false));
  saved.addEventListener("click", () => changeView(true));

  $("#dish").addEventListener("close", () => {
    if (savedOnly) {
      const id = grid.querySelector(":focus")?.dataset.foodId;
      renderSaved();

      (grid.querySelector(`[data-food-id="${id}"]`) || saved).focus();
    }
  });

  async function load(requestedPage) {
    const request = ++latestRequest;

    status.textContent = "Loading dishes…";

    const parameters = new URLSearchParams(filters);
    parameters.set("page", requestedPage);

    try {
      const { result: dishes, response } =
        await api(`/api/search?${parameters}`);

      if (request !== latestRequest) return;

      currentPage = requestedPage;

      const count = Number(response.headers.get("X-Total-Count"));
      const pages = Math.ceil(count / 30);

      status.textContent = count
        ? `${number.format(count)} matching dishes`
        : "No dishes found.";

      renderCards(dishes);

      pagination.hidden = pages < 2;
      $("#pageNumber").textContent = `Page ${currentPage} of ${pages}`;
      $("#previous").disabled = currentPage === 1;
      $("#next").disabled = currentPage >= pages;

    } catch (error) {
      if (request !== latestRequest) return;

      status.textContent = error.message;
      grid.replaceChildren();
      pagination.hidden = true;
    }
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    filters = new URLSearchParams(new FormData(form));
    load(1);
  });

  $("#previous").addEventListener("click", () => load(currentPage - 1));
  $("#next").addEventListener("click", () => load(currentPage + 1));

  grid.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-food-id]");
    if (!button) return;

    button.disabled = true;

    try {
      await showDish({ id: button.dataset.foodId });
    } catch (error) {
      notify(error.message);
    } finally {
      button.disabled = false;
    }
  });

  load(1);
}

// --------------------------------------------------
// GROCERY CHECKLIST
// --------------------------------------------------

function grocery() {
  const ingredients = new Map();

  for (const meal of mealsOf(state.plan)) {
    for (const item of meal.ingredients
      .split(";")
      .map((value) => value.trim())
      .filter(Boolean)) {

      const name = item.toLowerCase();

      if (!ingredients.has(name)) {
        ingredients.set(name, item);
      }
    }
  }

  const list = $("#groceryList");
  const empty = $("#groceryEmpty");
  const progress = $("#groceryProgress");
  const search = $("#ingredientSearch");
  const outstanding = $("#outstandingOnly");

  const checked = new Set(state.checked || []);

  const entries = [...ingredients.entries()].sort(
    (first, second) => first[1].localeCompare(second[1])
  );

  if (!entries.length) {
    empty.textContent = "Ingredient information is unavailable for this plan.";
    empty.hidden = false;
    return;
  }

  $("#grocerySummary").hidden = false;
  progress.max = entries.length;

  const rows = [];

  function refreshList() {
    const count = entries.filter(([name]) => checked.has(name)).length;

    progress.value = count;

    $("#groceryProgressText").textContent =
      count === entries.length
        ? `Shopping complete · ${count} of ${entries.length} checked`
        : `${count} of ${entries.length} checked · ${entries.length - count} left`;

    const query = search.value.trim().toLowerCase();
    let visible = 0;

    for (const { label, name } of rows) {
      label.hidden =
        !name.includes(query) ||
        (outstanding.checked && checked.has(name));

      if (!label.hidden) visible++;
    }

    list.hidden = visible === 0;
    empty.hidden = visible > 0;

    empty.textContent =
      outstanding.checked && count === entries.length
        ? "All ingredients are checked off."
        : "No ingredients match your filters.";
  }

  async function syncGrocery() {
    await api("/api/grocery/sync", {
      items: entries.map(([name, value]) => ({
        name: value,
        quantity: "1",
        purchased: checked.has(name)
      }))
    });
  }

  for (const [name, value] of entries) {
    const label = document.createElement("label");
    const input = document.createElement("input");
    const text = document.createElement("span");

    input.type = "checkbox";
    input.checked = checked.has(name);
    text.textContent = value;

    input.addEventListener("change", async () => {
      if (input.checked) checked.add(name);
      else checked.delete(name);

      saveState({ ...state, checked: [...checked] });

      refreshList();

      try {
        await syncGrocery();
      } catch (error) {
        notify(error.message);
      }

      if (label.hidden) {
        const index = rows.findIndex((row) => row.label === label);

        const next =
          rows.slice(index + 1).find((row) => !row.label.hidden) ||
          rows.find((row) => !row.label.hidden);

        (next?.input || outstanding).focus();
      }
    });

    label.append(input, text);
    list.append(label);

    rows.push({ label, input, name });
  }

  search.addEventListener("input", refreshList);
  outstanding.addEventListener("change", refreshList);

  refreshList();
}

// --------------------------------------------------
// PAGE INITIALIZATION
// --------------------------------------------------

const renderers = {
  home,
  planner,
  week,
  nutrition,
  foods: catalog,
  grocery,
  pantry: discover,
  mood: discover,
  insights: discover,
  diversity: discover,
  hydration: discover
};

async function initializePage() {
  try {
    // /api/data is the established saved-data endpoint in existing installs.
    const { result } = await api("/api/data");
    const savedRecipes = (Array.isArray(result.recipes) ? result.recipes : [])
      .map((item) => item.recipe_data)
      .filter((recipe) => recipe && typeof recipe === "object" && recipe.id != null);
    const nextState = { ...state, favorites: savedRecipes };

    if (!nextState.plan && result.latest_plan?.plan_data) {
      nextState.plan = result.latest_plan.plan_data;
      nextState.profile = result.latest_plan.profile_data || nextState.profile;
    }

    if (Array.isArray(result.grocery) && result.grocery.length) {
      nextState.checked = result.grocery
        .filter((item) => item.is_purchased)
        .map((item) => String(item.item_name).toLowerCase());
    }

    saveState(nextState);

    if (Array.isArray(result.hydration) && result.hydration.length) {
      const now = new Date();
      const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
      localStorage.setItem(
        `nutriai:water-log:${account}:${today}`,
        JSON.stringify(result.hydration.map((entry) => ({
          ml: entry.amount_ml,
          time: entry.display_time || ""
        })))
      );
    }

    if (result.hydration_pet) {
      localStorage.setItem(`nutriai:hydration-pet:${account}`, JSON.stringify({
        xp: result.hydration_pet.xp,
        goal: result.hydration_pet.daily_goal_ml,
        badges: result.hydration_pet.badges || []
      }));
    }
  } catch (error) {
    notify(`Saved recipes could not be loaded: ${error.message}`);
  }

  if ($("#emptyPlan") && !state.plan) {
    $("#emptyPlan").hidden = false;
  } else {
    renderers[page]?.();
  }
}

initializePage();

// --------------------------------------------------
// PANTRY, MOOD, NUTRITION INSIGHTS AND HYDRATION
// --------------------------------------------------

function discover() {
  const renderResults = (target, items, emptyText) => {
    const root = $(target);

    root.innerHTML = items.length
      ? items.map((dish) => `
        <article class="discover-card">
          <div>
            <strong>${escapeHtml(dish.name)}</strong>
            <p class="muted">
              ${escapeHtml(dish.category)} · ${escapeHtml(dish.diet)} ·
              ${dish.calories == null
                ? "Nutrition unavailable"
                : `${number.format(dish.calories)} kcal ${escapeHtml(dish.basis || "")}`}
            </p>
            ${dish.matched_ingredients
              ? `<small>Matched: ${dish.matched_ingredients.map(escapeHtml).join(", ")}</small>`
              : ""}
          </div>
          <button class="btn" type="button" data-discover-food="${dish.id}">
            Details
          </button>
        </article>`).join("")
      : `<p class="muted">${escapeHtml(emptyText)}</p>`;
  };

  async function openResult(event) {
    const button = event.target.closest("[data-discover-food]");
    if (!button) return;

    button.disabled = true;

    try {
      await showDish({ id: button.dataset.discoverFood });
    } catch (error) {
      notify(error.message);
    } finally {
      button.disabled = false;
    }
  }

  // PANTRY
  if ($("#pantryForm")) {
    $("#pantryForm").addEventListener("submit", async (event) => {
      event.preventDefault();

      const form = event.currentTarget;
      const data = Object.fromEntries(new FormData(form));

      const ingredients = data.ingredients
        .split(",")
        .map((x) => x.trim())
        .filter(Boolean);

      try {
        const { result } = await api("/api/pantry", {
          ingredients,
          diet: data.diet,
          preferences: state.foodFeedback || {}
        });

        await api("/api/pantry/save", {
          items: ingredients.map((name) => ({
            name,
            quantity: "1"
          }))
        });

        renderResults(
          "#pantryResults",
          result.matches,
          "No catalog dishes matched those ingredients. Try broader ingredient names."
        );

        $("#pantryResults").insertAdjacentHTML(
          "afterbegin",
          `<p class="muted">${result.total_matches} matches · ${escapeHtml(result.note)}</p>`
        );

      } catch (error) {
        notify(error.message);
      }
    });
  }

  // MOOD
  if ($("#moodForm")) {
    $("#moodForm").addEventListener("submit", async (event) => {
      event.preventDefault();

      const data = Object.fromEntries(new FormData(event.currentTarget));

      try {
        const { result } = await api("/api/mood", {
          ...data,
          preferences: state.foodFeedback || {}
        });

        await api("/api/mood/save", {
          mood: data.mood,
          preferences: state.foodFeedback || {}
        });

        renderResults(
          "#moodResults",
          result.matches,
          "No matches found for this selection."
        );

        $("#moodResults").insertAdjacentHTML(
          "afterbegin",
          `<p class="muted">${result.total_matches} matches · ${escapeHtml(result.explanation)}</p>`
        );

      } catch (error) {
        notify(error.message);
      }
    });
  }

  if ($("#pantryResults")) {
    $("#pantryResults").addEventListener("click", openResult);
  }

  if ($("#moodResults")) {
    $("#moodResults").addEventListener("click", openResult);
  }

  // NUTRITION INSIGHTS
  if ($("#nutritionInsightsButton")) {
    bindAction($("#nutritionInsightsButton"), async () => {
      if (!state.plan) {
        throw new Error("Generate a weekly plan first.");
      }

      const { result } = await api("/api/nutrition-insights", {
        plan: state.plan
      });

      await api("/api/nutrition-history", {
        nutrition_data: result
      });

      const labels = {
        calories: "Calories (kcal)",
        protein: "Protein (g)",
        carbohydrates: "Carbohydrates (g)",
        fat: "Fat (g)",
        fibre: "Fibre (g)"
      };

      $("#nutritionInsightsResults").innerHTML = `
        <div class="diversity-metrics">
          ${Object.entries(result.daily_averages).map(([key, value]) => `
            <div>
              <strong>${value == null ? "—" : number.format(value)}</strong>
              <span>${labels[key] || escapeHtml(key)}</span>
            </div>`).join("")}
        </div>
        <p>
          <strong>Missing recorded values:</strong>
          ${Object.entries(result.missing_values).map(([key, value]) =>
            `${labels[key] || escapeHtml(key)}: ${value}`
          ).join(" · ")}
        </p>
        <p class="muted">${escapeHtml(result.note)}</p>`;
    });
  }

  // FOOD DIVERSITY
  if ($("#diversityButton")) {
    bindAction($("#diversityButton"), async () => {
      if (!state.plan) {
        throw new Error("Generate a weekly plan first.");
      }

      const { result } = await api("/api/diversity", {
        plan: state.plan
      });

      $("#diversityResults").innerHTML = `
        <div class="diversity-metrics">
          <div><strong>${result.unique_dishes}/${result.total_meals}</strong><span>Unique dishes</span></div>
          <div><strong>${result.repeated_meals}</strong><span>Repeated meals</span></div>
          <div><strong>${result.categories_represented}</strong><span>Meal categories</span></div>
          <div><strong>${result.regions_represented}</strong><span>Recorded regions</span></div>
        </div>
        <p>${result.score}% ${escapeHtml(result.score_label)}</p>
        <p class="muted">${escapeHtml(result.note)}</p>`;
    });
  }

  // HYDRATION
  if (!$("#waterMl")) return;

  const now = new Date();

  const today =
    `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;

  const hydrationKey = `nutriai:water-log:${account}:${today}`;
  const petKey = `nutriai:hydration-pet:${account}`;

  let log = [];
  let pet = {
    xp: 0,
    goal: 2000,
    badges: []
  };

  try {
    const saved = JSON.parse(localStorage.getItem(hydrationKey) || "[]");

    if (Array.isArray(saved)) {
      log = saved
        .filter((e) => e && typeof e.time === "string")
        .slice(-99);
    }
  } catch {
    log = [];
  }

  try {
    pet = {
      ...pet,
      ...JSON.parse(localStorage.getItem(petKey) || "{}")
    };
  } catch {}

  const persist = () => {
    localStorage.setItem(hydrationKey, JSON.stringify(log));
    localStorage.setItem(petKey, JSON.stringify(pet));

    api("/api/hydration/sync", {
      log,
      pet
    }).catch((error) => {
      notify(error.message);
    });
  };

  const waterTotal = () =>
    log.reduce((sum, e) => sum + (Number(e.ml) || 0), 0);

  const earned = (badge) => {
    if (!pet.badges.includes(badge)) {
      pet.badges.push(badge);
    }
  };

  const refresh = () => {
    const ml = waterTotal();
    const goal = Math.max(250, Number(pet.goal) || 2000);
    const pct = Math.min(100, Math.round(ml / goal * 100));

    $("#waterMl").textContent = `${ml.toLocaleString()} ml`;
    $("#waterCount").textContent = `${log.length} servings logged today`;
    $("#waterGoalText").textContent = `${goal.toLocaleString()} ml`;

    $("#waterRemaining").textContent =
      ml >= goal
        ? "Daily goal reached! 🎉"
        : `${(goal - ml).toLocaleString()} ml to go`;

    $("#waterPercent").textContent = `${pct}%`;
    $("#waterProgress").style.width = `${pct}%`;

    const mood =
      pct >= 100
        ? ["🎉", "You did it! Aqua is celebrating with you!"]
        : pct >= 70
          ? ["★", "So close! Aqua is super excited!"]
          : pct >= 25
            ? ["◡", "Aqua is feeling happy. Keep it up!"]
            : ["﹏", "Aqua is waiting for the first sip!"];

    $("#aquaFace").textContent = mood[0];
    $("#aquaMessage").textContent = mood[1];

    $("#aquaPet").classList.toggle(
      "aqua-celebrate",
      pct >= 100
    );

    const level = Math.min(5, Math.floor(pet.xp / 100) + 1);

    const names = [
      "Tiny Drop",
      "Happy Drop",
      "Aqua Explorer",
      "Ocean Guardian",
      "Aqua Legend"
    ];

    $("#aquaLevel").textContent =
      `💧 ${names[level - 1]} · Level ${level}`;

    $("#aquaRewardLevel").textContent = `Level ${level}`;
    $("#aquaXp").textContent = `${pet.xp} XP`;

    $("#aquaXpProgress").style.width =
      `${level === 5 ? 100 : pet.xp % 100}%`;

    $("#aquaNextReward").textContent =
      level === 5
        ? "Aqua reached the highest level!"
        : `${100 - pet.xp % 100} XP to the next level`;

    if (log.length) earned("First Sip");
    if (pct >= 100) earned("Daily Goal Champion");

    $("#hydrationBadges").innerHTML =
      ["First Sip", "Daily Goal Champion", "Water Warrior"]
        .map((badge, i) => `
          <span class="hydration-badge ${pet.badges.includes(badge) ? "earned" : "locked"}">
            ${["💧", "🏆", "🌊"][i]} ${badge}
          </span>`).join("");

    $("#waterLog").innerHTML = log.length
      ? `
        <h3>Today's water log</h3>
        <ol>
          ${log.slice().reverse().map((e) => `
            <li>
              <span>💧 ${Number(e.ml) ? `${e.ml} ml` : "Previous serving (volume unknown)"}</span>
              <time>${escapeHtml(e.time)}</time>
            </li>`).join("")}
        </ol>`
      : `<p class="muted water-empty">No drinks logged yet. Add your first glass when you're ready.</p>`;

    persist();
  };

  document.querySelectorAll(".water-add").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (log.length >= 99) return;

      log.push({
        ml: Number(btn.dataset.ml),
        time: new Date().toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit"
        })
      });

      pet.xp += 10;
      refresh();

      btn.classList.add("added");

      setTimeout(() => {
        btn.classList.remove("added");
      }, 350);
    });
  });

  $("#waterMinus").addEventListener("click", () => {
    if (!log.length) return;

    const last = log.pop();

    if (Number(last.ml)) {
      pet.xp = Math.max(0, pet.xp - 10);
    }

    refresh();
  });

  $("#waterReset").addEventListener("click", () => {
    if (!confirm("Clear today's water log?")) return;

    log = [];
    refresh();
  });

  $("#waterGoal").value = pet.goal;

  $("#saveWaterGoal").addEventListener("click", () => {
    const value = Number($("#waterGoal").value);

    if (!Number.isFinite(value) || value < 250 || value > 6000) {
      notify("Choose a personal goal between 250 and 6000 ml.");
      return;
    }

    pet.goal = value;
    refresh();
    notify("Your hydration goal was updated.");
  });

  refresh();
}
