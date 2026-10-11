from Main_DataBase import Database

db = Database("recipedatabase.db")

 # Step 1: Add a test recipe
recipe_id = db.add_data(("Omelette", "Breakfast", "French", None, "Chef Marie", "15 Min"))
print(f"Added Recipe ID: {recipe_id}")

# Step 2: Add ingredients (add_ingredient returns each one's id)
egg_id = db.add_ingredient(recipe_id, "Egg", "2", position=1)
cheese_id = db.add_ingredient(recipe_id, "Cheese", "1/4 cup", position=2)
salt_id = db.add_ingredient(recipe_id, "Salt", "1/4 tsp", position=3)
pepper_id = db.add_ingredient(recipe_id, "Pepper", "1/8 tsp", position=4)
print("Ingredients added.")

# Step 3: Add instructions
db.add_instruction(recipe_id, 1, "Beat eggs with salt and pepper.")
db.add_instruction(recipe_id, 2, "Pour mixture into a hot non-stick pan.")
db.add_instruction(recipe_id, 3, "Sprinkle cheese and fold when cooked.")
print("Instructions added.")

# Step 4: Add connections (linking ingredients to instructions)
cur = db.conn.cursor()
cur.execute(
    "INSERT INTO connections (recipe_id, step_number, ingredient_id) VALUES (?, ?, ?)",
    (recipe_id, 1, egg_id)
)
cur.execute(
    "INSERT INTO connections (recipe_id, step_number, ingredient_id) VALUES (?, ?, ?)",
    (recipe_id, 1, salt_id)
)
cur.execute(
    "INSERT INTO connections (recipe_id, step_number, ingredient_id) VALUES (?, ?, ?)",
    (recipe_id, 1, pepper_id)
)
cur.execute(
    "INSERT INTO connections (recipe_id, step_number, ingredient_id) VALUES (?, ?, ?)",
    (recipe_id, 3, cheese_id)
)
db.conn.commit()
print("Connections added.")

# Verify data before delete
print("Data before deletion:")
cur.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,))
print("Recipe:", cur.fetchall())
cur.execute("SELECT * FROM ingredients WHERE recipe_id = ?", (recipe_id,))
print("Ingredients:", cur.fetchall())
cur.execute("SELECT * FROM instructions WHERE recipe_id = ?", (recipe_id,))
print("Instructions:", cur.fetchall())
cur.execute("SELECT * FROM connections WHERE recipe_id = ?", (recipe_id,))
print("Connections:", cur.fetchall())

# Step 5: Delete the recipe
db.delete_recipe(recipe_id)
print(f"Deleted Recipe ID: {recipe_id}")

# Verify cascading deletes
print("Data after deletion:")
cur.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,))
print("Recipe:", cur.fetchall())
cur.execute("SELECT * FROM ingredients WHERE recipe_id = ?", (recipe_id,))
print("Ingredients:", cur.fetchall())
cur.execute("SELECT * FROM instructions WHERE recipe_id = ?", (recipe_id,))
print("Instructions:", cur.fetchall())
cur.execute("SELECT * FROM connections WHERE recipe_id = ?", (recipe_id,))
print("Connections:", cur.fetchall())
