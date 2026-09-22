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
    ingredients_split = [split_ingredient(ing) for ing in ingredients_raw]

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
    # Matches a leading quantity (numbers, fractions, 'and', ranges) optionally followed by a unit
    match = re.match(
        r'^([\d/.\s]+(?:and\s+[\d/.\s]+)?)\s*(' + '|'.join(COMMON_UNITS) + r')?\b\.?\s*',
        text,
        re.IGNORECASE
    )
    if match and match.group(0).strip():
        measurement = match.group(0).strip()
        name = text[match.end():].strip()
        if name:
            return measurement, name
    return '', text

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

    conn.close()
    return render_template(
        'home.html',
        latest_recipes=latest_recipes,
        seasonal_recipes=seasonal_recipes,
        current_season=current_season
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

    # Add ingredients
    ingredient_names = request.form.getlist('ingredient_name[]')
    measurements = request.form.getlist('measurement[]')
    for ingredient_name, measurement in zip(ingredient_names, measurements):
        if not ingredient_name:
            continue
        try:
            cur.execute(
                """
                INSERT INTO ingredients (recipe_id, ingredient_name, measurement)
                VALUES (?, ?, ?)
                """,
                (recipe_id, ingredient_name, measurement)
            )
        except sqlite3.IntegrityError:
            # Duplicate ingredient name for this recipe — skip rather than crash
            continue

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

    conn.close()
    return render_template('all.html', recipes=recipes, search_query=search_query)

# define a route and a view function
@app.route('/all-recipes/<int:id>')
def recipe_details(id):
    conn = get_db_connection() 
    recipe = conn.execute('SELECT * FROM recipes WHERE id = ?', (id,)).fetchone()  # Use fetchone() instead of fetchall()
    ingredients = conn.execute('SELECT ingredient_name, measurement FROM ingredients WHERE recipe_id = ?', (id,)).fetchall()
    instructions = conn.execute('SELECT step_number, instruction FROM instructions WHERE recipe_id = ? ORDER BY step_number', (id,)).fetchall()
    conn.close()
    return render_template('index.html', recipe=recipe, ingredients=ingredients, instructions=instructions)

@app.route('/<string:category>')
def category_recipes(category):
    conn = get_db_connection()
    recipes = conn.execute('SELECT * FROM recipes WHERE type = ?', (category.capitalize(),)).fetchall()
    conn.close()
    return render_template('category.html', recipes=recipes, category=category.capitalize())

# delete a recipe
@app.route('/delete_recipe/<int:recipe_id>', methods=['POST'])
def delete_recipe(recipe_id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM recipes WHERE id = ?", (recipe_id,))
        conn.commit()
        if cur.rowcount == 0:
            return f"No recipe found with ID {recipe_id}.", 404
        else:
            return f"Recipe with ID {recipe_id} deleted successfully.", 200
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
            
            for name, meas in zip(request.form.getlist('ingredient_name[]'), request.form.getlist('measurement[]')):
                if name and meas:
                    cur.execute("""
                        INSERT INTO ingredients (recipe_id, ingredient_name, measurement)
                        VALUES (?, ?, ?)
                    """, (id, name, meas))
            
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
        cur.execute("SELECT ingredient_name, measurement FROM ingredients WHERE recipe_id = ?", (id,))
        ingredients = cur.fetchall()
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