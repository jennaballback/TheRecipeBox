from flask import Flask, render_template, request, redirect, url_for
import sqlite3
from werkzeug.utils import secure_filename
import os
import datetime

import requests
from bs4 import BeautifulSoup
import json
import re
import uuid
from itertools import groupby

from Main_DataBase import upgrade_schema

# create a Flask app instance
app = Flask(__name__)
DATABASE = "recipedatabase.db"

# Helper function to get a database connection 
def get_db_connection(): 
    db_path = os.path.abspath(DATABASE)
    print("Using Database FIle:", db_path)

    # conn = sqlite3.connect(DATABASE) 
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row 
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

# Bring an older database file up to the current schema before serving anything
_conn = sqlite3.connect(os.path.abspath(DATABASE))
upgrade_schema(_conn)
_conn.close()


def read_ingredient_rows(form):
    """Reads the ingredient list from the Add/Edit form as (section, measurement, name) rows.

    The form sends one entry per row in `row_kind[]`: 'section' rows are headings like
    "Topping" that apply to the ingredients below them, 'ingredient' rows are ingredients.
    """
    kinds = form.getlist('row_kind[]')
    names = form.getlist('ingredient_name[]')
    measurements = form.getlist('measurement[]')
    if len(kinds) != len(names):
        kinds = ['ingredient'] * len(names)

    rows = []
    section = None
    for kind, name, measurement in zip(kinds, names, measurements):
        name = (name or '').strip()
        if kind == 'section':
            section = name or None
        elif name:
            rows.append((section, (measurement or '').strip(), name))
    return rows


def save_ingredients(cur, recipe_id, rows):
    for position, (section, measurement, name) in enumerate(rows, start=1):
        cur.execute(
            """
            INSERT INTO ingredients (recipe_id, section, position, ingredient_name, measurement)
            VALUES (?, ?, ?, ?, ?)
            """,
            (recipe_id, section, position, name, measurement)
        )


def load_ingredients(conn, recipe_id):
    return conn.execute(
        "SELECT section, measurement, ingredient_name FROM ingredients WHERE recipe_id = ? ORDER BY position, id",
        (recipe_id,)
    ).fetchall()

def get_current_season():
    month = datetime.date.today().month
    if month in (12, 1, 2):
        return "Winter"
    elif month in (3, 4, 5):
        return "Spring"
    elif month in (6, 7, 8):
        return "Summer"
    else:
        return "Fall"

def get_cuisines(conn, recipe_type=None):
    """Distinct cuisines in the database (optionally for one meal type), for the filter pills."""
    query = "SELECT DISTINCT cuisine FROM recipes WHERE cuisine IS NOT NULL AND cuisine != ''"
    params = []
    if recipe_type:
        query += " AND type = ?"
        params.append(recipe_type)
    query += " ORDER BY cuisine"
    return [row['cuisine'] for row in conn.execute(query, params).fetchall()]

def parse_iso_duration(duration):
    """Converts an ISO 8601 duration like 'PT1H30M' into '1 hr 30 min'."""
    if not duration:
        return None
    match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?', duration)
    if not match:
        return duration
    hours, minutes = match.groups()
    parts = []
    if hours:
        parts.append(f"{hours} hr")
    if minutes:
        parts.append(f"{minutes} min")
    return " ".join(parts) if parts else duration


def is_recipe_type(item):
    t = item.get('@type')
    if isinstance(t, list):
        return 'Recipe' in t
    return t == 'Recipe'


def find_recipe_jsonld(soup):
    """Searches all JSON-LD script blocks on the page for one describing a Recipe."""
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string)
        except (TypeError, ValueError):
            continue
        candidates = data if isinstance(data, list) else [data]
        for item in candidates:
            if not isinstance(item, dict):
                continue
            if '@graph' in item:
                for sub in item['@graph']:
                    if isinstance(sub, dict) and is_recipe_type(sub):
                        return sub
            if is_recipe_type(item):
                return item
    return None


def extract_recipe_data(recipe_json):
    name = recipe_json.get('name')

    author = recipe_json.get('author')
    if isinstance(author, list):
        author = author[0] if author else None
    if isinstance(author, dict):
        author = author.get('name')

    ingredients_raw = recipe_json.get('recipeIngredient', [])
    ingredients_split = [(None, *split_ingredient(ing)) for ing in ingredients_raw]

    instructions = []
    for step in recipe_json.get('recipeInstructions', []):
        if isinstance(step, dict):
            text = step.get('text') or step.get('name')
            if text:
                instructions.append(text)
        elif isinstance(step, str):
            instructions.append(step)

    image = recipe_json.get('image')
    if isinstance(image, list):
        image = image[0] if image else None
    if isinstance(image, dict):
        image = image.get('url')

    cuisine = recipe_json.get('recipeCuisine')
    if isinstance(cuisine, list):
        cuisine = cuisine[0] if cuisine else None

    category = recipe_json.get('recipeCategory')
    if isinstance(category, list):
        category = category[0] if category else None

    yield_value = recipe_json.get('recipeYield')
    if isinstance(yield_value, list):
        yield_value = yield_value[0] if yield_value else None

    return {
        'name': name,
        'author': author,
        'cuisine': cuisine,
        'category': category,
        'total_time': parse_iso_duration(recipe_json.get('totalTime')),
        'yield': yield_value,
        'image': image,
        'ingredients': ingredients_split,
        'instructions': instructions
    }

COMMON_UNITS = [
    'cups', 'cup', 'tablespoons', 'tablespoon', 'tbsp', 'teaspoons', 'teaspoon', 'tsp',
    'pounds', 'pound', 'lbs', 'lb', 'ounces', 'ounce', 'oz', 'grams', 'gram', 'g',
    'kilograms', 'kg', 'milliliters', 'ml', 'liters', 'l', 'pinch', 'pinches',
    'cloves', 'clove', 'slices', 'slice', 'cans', 'can', 'packages', 'package'
]

def split_ingredient(text):
    """Best-effort split of a raw ingredient string into (measurement, name)."""
    # Matches a leading quantity (numbers, fractions, 'and', ranges) optionally followed by a unit,
    # plus a weight in brackets after it, so "1/2 cup (100g) sugar" keeps "(100g)" with the amount
    match = re.match(
        r'^([\d/.\s]+(?:and\s+[\d/.\s]+)?)\s*(\([^)]*\)\s*)?(' + '|'.join(COMMON_UNITS) + r')?\b\.?\s*(\([^)]*\)\s*)?',
        text,
        re.IGNORECASE
    )
    if match and match.group(0).strip():
        measurement = match.group(0).strip()
        name = text[match.end():].strip()
        if name:
            return measurement, name
    return '', text

# Ingredient lists in the page's HTML, from the recipe card plugins most food blogs use.
# The recipe data (JSON-LD) is a flat list, so section headings like "Topping" only exist here.
INGREDIENT_CONTAINERS = [
    '.tasty-recipes-ingredients',          # Tasty Recipes (Sally's Baking Addiction, ...)
    '.wprm-recipe-ingredients-container',  # WP Recipe Maker
    '.mv-create-ingredients',              # Mediavine Create
]
HEADING_TAGS = ['h2', 'h3', 'h4', 'h5', 'h6']


def clean_text(tag):
    text = tag.get_text(' ', strip=True)
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'\(\s+', '(', text)
    text = re.sub(r'\s+([),.;:])', r'\1', text)
    return text.strip()


def find_ingredient_groups(soup):
    """Reads the ingredient list with its section headings from the page's HTML.

    Returns a list of (section, text) or None when the page has no sections to keep.
    """
    for selector in INGREDIENT_CONTAINERS:
        box = soup.select_one(selector)
        if not box:
            continue
        rows = []
        section = None
        found_section = False
        for tag in box.find_all(lambda t: t.name in HEADING_TAGS or t.name == 'li'
                                or 'wprm-recipe-group-name' in (t.get('class') or [])):
            text = clean_text(tag)
            if not text:
                continue
            if tag.name == 'li':
                if tag.find('li'):
                    continue  # a list wrapping other items, not an ingredient itself
                rows.append((section, text))
            elif text.lower().rstrip(':') != 'ingredients':
                section = text.rstrip(':')
                found_section = True
        if found_section and rows:
            return rows
    return None


# define a route for the root URL
@app.route("/")
def index():
    conn = get_db_connection()
    cur = conn.cursor()

    # Latest recipes: most recently added, limit to a handful
    cur.execute("SELECT * FROM recipes ORDER BY id DESC LIMIT 6")
    latest_recipes = cur.fetchall()

    # Seasonal recipes: matching the current season
    current_season = get_current_season()
    cur.execute("SELECT * FROM recipes WHERE season = ? LIMIT 6", (current_season,))
    seasonal_recipes = cur.fetchall()

    # Recipe counts per meal type, for the category tiles
    cur.execute("SELECT type, COUNT(*) AS n FROM recipes GROUP BY type")
    category_counts = {row['type']: row['n'] for row in cur.fetchall() if row['type']}
    total_recipes = sum(category_counts.values())

    conn.close()
    return render_template(
        'home.html',
        latest_recipes=latest_recipes,
        seasonal_recipes=seasonal_recipes,
        current_season=current_season,
        category_counts=category_counts,
        total_recipes=total_recipes
    )

@app.route('/import-recipe', methods=['GET', 'POST'])
def import_recipe():
    if request.method == 'GET':
        return redirect(url_for('add'))

    url = request.form.get('url', '').strip()
    if not url:
        return render_template('add.html', import_error="Please enter a URL.")

    try:
        response = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
        response.raise_for_status()
    except requests.RequestException:
        return render_template('add.html', import_error="Couldn't reach that page. Check the link and try again.")

    soup = BeautifulSoup(response.text, 'html.parser')
    recipe_json = find_recipe_jsonld(soup)

    if not recipe_json:
        return render_template('add.html', import_error="Couldn't find recipe data on that page. Try entering it manually.")

    data = extract_recipe_data(recipe_json)

    # Use the page's own list when it groups ingredients under headings, as long as it
    # has at least everything the recipe data lists
    groups = find_ingredient_groups(soup)
    if groups and len(groups) >= len(data['ingredients']):
        data['ingredients'] = [(section, *split_ingredient(text)) for section, text in groups]


    # Download the recipe's photo now, so it's ready to attach if the form is saved
    if data['image']:
        try:
            img_resp = requests.get(data['image'], timeout=10., headers={'User-Agent': 'Mozilla/5.0'})
            img_resp.raise_for_status()
            ext = '.jpg'
            if '.' in data['image'].split('/')[-1]:
                ext = '.' + data['image'].split('.')[-1].split('?')[0][:4]
            filename = f"imported_{uuid.uuid4().hex}{ext}"
            saved_path = f"static/images/{filename}"
            with open(saved_path, 'wb') as f:
                f.write(img_resp.content)
            data['image'] = f"/{saved_path}"
        except requests.RequestException:
            data['image'] = None

    return render_template('add.html', imported=data)

@app.route('/add')
def add():
    
    return render_template('add.html')

@app.route('/submit', methods=['POST'])
def submit():
    # Get form data
    name = request.form.get('name')
    category = request.form.get('category')
    cuisine = request.form.get('cuisine')
    season = request.form.get('season')
    author = request.form.get('author')
    time = request.form.get('total_time')
    yield_value = request.form.get('yield')
    photo = request.files.get('photo')

    if not name or not category or not time:
        return "Error: Missing required fields", 400

    # Insert into the database
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute(
            """
            INSERT INTO recipes (name, type, cuisine, season, author, total_time, yield, image)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (name, category, cuisine, season, author, time, yield_value, None)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return "Error: A recipe with this name, type, and cuisine already exists.", 400
    
    print("Recipe inserted, lastrowid: ", cur.lastrowid)
    recipe_id = cur.lastrowid  # Get the ID of the inserted recipe

    if photo and photo.filename:
        filename = secure_filename(photo.filename)
        image_path = f"static/images/{recipe_id}_{filename}"
        photo.save(image_path)
        cur.execute("UPDATE recipes SET image = ? WHERE id = ?", (f"/{image_path}", recipe_id))
        conn.commit()
    elif request.form.get('imported_image_path'):
        cur.execute("UPDATE recipes SET image = ? WHERE id = ?", (request.form.get('imported_image_path'), recipe_id))
        conn.commit()

    print("Recipe inserted, lastrowid: ", cur.lastrowid)
    # Verify recipe_id
    if not recipe_id:
        print("ERROR: lastrowid is NULL - Checking database")
        cur.execute("SELECT * FROM recipes;")
        print("Existing Recipes:", cur.fetchall())  # Print current recipes
        return "Error: Recipe ID is NULL after insert", 500
    
    print("Recipe ID:", recipe_id)

    # Add ingredients, with any section headings
    save_ingredients(cur, recipe_id, read_ingredient_rows(request.form))

    # Add instructions
    instructions = request.form.getlist('instruction[]')
    for step_number, instruction in enumerate(instructions, start=1):
        cur.execute(
            """
            INSERT INTO instructions (recipe_id, step_number, instruction)
            VALUES (?, ?, ?)
            """,
            (recipe_id, step_number, instruction)
        )

    conn.commit()
    conn.close()

    # Redirect to all recipes page
    return redirect('/all-recipes')

# view all the recipes and supports the search bar
@app.route('/all-recipes')
def all_recipes():
    conn = get_db_connection() 
    cur = conn.cursor()

    # Get the search query from the request, default to empty string if not provided
    search_query = request.args.get('search', '').strip()
    cuisine_filter = request.args.get('cuisine', '').strip()
    season_filter = request.args.get('season', '').strip()

    # Build the SQL query dynamically
    query = "SELECT * FROM recipes WHERE 1=1"
    params = []
    if search_query:
        # Search across name, type, and cuisine with LIKE operator
        query += " AND (name LIKE ? OR type LIKE ? OR cuisine LIKE ?)"
        params.extend([f'%{search_query}%'] * 3)

    if cuisine_filter:
        query += " AND cuisine = ?"
        params.append(cuisine_filter)

    if season_filter:
        query += " AND season = ?"
        params.append(season_filter)

    # Execute the query with parameters to prevent SQL injection
    cur.execute(query, params)
    recipes = cur.fetchall()
    cuisines = get_cuisines(conn)

    conn.close()
    return render_template(
        'all.html',
        recipes=recipes,
        search_query=search_query,
        cuisines=cuisines,
        cuisine_filter=cuisine_filter,
        season_filter=season_filter
    )

# define a route and a view function
@app.route('/all-recipes/<int:id>')
def recipe_details(id):
    conn = get_db_connection() 
    recipe = conn.execute('SELECT * FROM recipes WHERE id = ?', (id,)).fetchone()  # Use fetchone() instead of fetchall()
    ingredients = load_ingredients(conn, id)
    instructions = conn.execute('SELECT step_number, instruction FROM instructions WHERE recipe_id = ? ORDER BY step_number', (id,)).fetchall()
    conn.close()
    # Consecutive ingredients under the same heading, e.g. [("Topping", [...]), ("Muffins", [...])]
    ingredient_groups = [(section, list(rows)) for section, rows in groupby(ingredients, key=lambda row: row['section'])]
    return render_template('index.html', recipe=recipe, ingredients=ingredients,
                           ingredient_groups=ingredient_groups, instructions=instructions)

@app.route('/<string:category>')
def category_recipes(category):
    category = category.capitalize()
    cuisine_filter = request.args.get('cuisine', '').strip()
    season_filter = request.args.get('season', '').strip()

    query = "SELECT * FROM recipes WHERE type = ?"
    params = [category]
    if cuisine_filter:
        query += " AND cuisine = ?"
        params.append(cuisine_filter)
    if season_filter:
        query += " AND season = ?"
        params.append(season_filter)

    conn = get_db_connection()
    recipes = conn.execute(query, params).fetchall()
    cuisines = get_cuisines(conn, category)
    conn.close()
    return render_template(
        'category.html',
        recipes=recipes,
        category=category,
        cuisines=cuisines,
        cuisine_filter=cuisine_filter,
        season_filter=season_filter
    )

# remove a deleted recipe's photo from static/images, unless another recipe still uses it
def delete_recipe_photo(cur, image):
    images_dir = os.path.abspath(os.path.join('static', 'images'))
    photo_path = os.path.abspath(image.lstrip('/'))
    if os.path.dirname(photo_path) != images_dir or not os.path.isfile(photo_path):
        return
    if cur.execute("SELECT 1 FROM recipes WHERE image = ?", (image,)).fetchone():
        return
    try:
        os.remove(photo_path)
    except OSError as e:
        print(f"Could not delete photo {photo_path}: {e}")

# delete a recipe
@app.route('/delete_recipe/<int:recipe_id>', methods=['POST'])
def delete_recipe(recipe_id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        row = cur.execute("SELECT image FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
        cur.execute("DELETE FROM recipes WHERE id = ?", (recipe_id,))
        conn.commit()
        if cur.rowcount == 0:
            return f"No recipe found with ID {recipe_id}.", 404
        if row and row['image']:
            delete_recipe_photo(cur, row['image'])
        return redirect(url_for('index'))
    except sqlite3.Error as e:
        conn.rollback()
        return f"Error deleting recipe: {e}", 500
    finally:
        conn.close()

@app.route('/modify-recipe/<int:id>', methods=['GET', 'POST'])
def modify_recipe(id):
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        if request.method == 'POST':
            cur.execute("SELECT id FROM recipes WHERE id = ?", (id,))
            if not cur.fetchone():
                conn.close()
                return "Recipe not found", 404
            
            name = request.form.get('name')
            recipe_type = request.form.get('type')

            if not name or not recipe_type:
                conn.close()
                return "Error: Name and type are required", 400

            cur.execute("""
                UPDATE recipes
                SET name = ?, type = ?, cuisine = ?, season = ?, author = ?, total_time = ?, yield = ?, image = ?
                WHERE id = ?
            """, (
                name,
                recipe_type,
                request.form.get('cuisine', None),
                request.form.get('season', None), 
                request.form.get('author', None),
                request.form.get('total_time', None),
                request.form.get('yield', None),
                request.form.get('image', None),
                id
            ))
            cur.execute("DELETE FROM ingredients WHERE recipe_id = ?", (id,))
            cur.execute("DELETE FROM instructions WHERE recipe_id = ?", (id,))
            conn.commit()
            
            save_ingredients(cur, id, read_ingredient_rows(request.form))
            
            instructions = request.form.getlist('instruction[]')
            for i, inst in enumerate(instructions, 1):
                if inst:
                    cur.execute("""
                        INSERT INTO instructions (recipe_id, step_number, instruction)
                        VALUES (?, ?, ?)
                    """, (id, i, inst))
            
            if 'photo' in request.files and request.files['photo'].filename:
                photo = request.files['photo']
                filename = secure_filename(photo.filename)
                photo_path = f"static/images/{id}_{photo.filename}"
                photo.save(photo_path)
                cur.execute("""
                    UPDATE recipes
                    SET image = ?
                    WHERE id = ?
                """, (f"/static/images/{id}_{photo.filename}", id))
            
            conn.commit()
            conn.close()
            return redirect(url_for('recipe_details', id=id))
        
        cur.execute("SELECT * FROM recipes WHERE id = ?", (id,))
        recipe = cur.fetchone()
        if not recipe:
            conn.close()
            return "Recipe not found", 404
        ingredients = load_ingredients(conn, id)
        cur.execute("SELECT step_number, instruction FROM instructions WHERE recipe_id = ? ORDER BY step_number", (id,))
        instructions = cur.fetchall()
        conn.close()
        return render_template('modify.html', recipe=recipe, ingredients=ingredients, instructions=instructions)
    except sqlite3.Error as e:
        conn.close()
        return f"Database error: {e}", 500

# run the app if this file is executed
if __name__ == '__main__':
    app.run(debug=True)