from sqlite3 import Error
import sqlite3 


def upgrade_schema(conn):
    """Updates a database created before ingredient sections existed. Safe to run every time.

    The old ingredients table allowed each ingredient name only once per recipe, which
    breaks recipes that use the same thing in two sections (brown sugar in the topping
    and the batter). SQLite can't drop a UNIQUE rule in place, so the table is rebuilt:
    make the new table, copy the rows across, then swap it in.
    """
    columns = [row[1] for row in conn.execute("PRAGMA table_info(ingredients)")]
    if not columns or 'section' in columns:
        return

    conn.commit()
    conn.execute("PRAGMA foreign_keys = OFF;")
    try:
        conn.executescript("""
            BEGIN;

            CREATE TABLE ingredients_new(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recipe_id INTEGER NOT NULL,
                section TEXT DEFAULT NULL,
                position INTEGER NOT NULL DEFAULT 0,
                ingredient_name TEXT NOT NULL,
                measurement TEXT,
                FOREIGN KEY (recipe_id) REFERENCES recipes (id) ON DELETE CASCADE
            );

            -- Keep each recipe's ingredients in the order they were added
            INSERT INTO ingredients_new (id, recipe_id, section, position, ingredient_name, measurement)
            SELECT id, recipe_id, NULL,
                   ROW_NUMBER() OVER (PARTITION BY recipe_id ORDER BY id),
                   ingredient_name, measurement
            FROM ingredients
            WHERE recipe_id IS NOT NULL AND ingredient_name IS NOT NULL;

            -- connections pointed at an ingredient by its name, which is no longer unique,
            -- so it now points at the ingredient's id instead
            CREATE TABLE connections_new(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recipe_id INTEGER,
                step_number INTEGER,
                ingredient_id INTEGER,
                FOREIGN KEY (recipe_id) REFERENCES recipes (id) ON DELETE CASCADE,
                FOREIGN KEY (recipe_id, step_number) REFERENCES instructions (recipe_id, step_number) ON DELETE CASCADE,
                FOREIGN KEY (ingredient_id) REFERENCES ingredients (id) ON DELETE CASCADE
            );

            INSERT INTO connections_new (id, recipe_id, step_number, ingredient_id)
            SELECT c.id, c.recipe_id, c.step_number, i.id
            FROM connections c
            JOIN ingredients i ON i.recipe_id = c.recipe_id AND i.ingredient_name = c.ingredient_name;

            DROP TABLE connections;
            DROP TABLE ingredients;
            ALTER TABLE ingredients_new RENAME TO ingredients;
            ALTER TABLE connections_new RENAME TO connections;

            COMMIT;
        """)
    except sqlite3.Error:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON;")



class Database:
    def __init__(self, recipe_database):
        self.recipe_database = recipe_database
        self.conn = self.create_connection()

        # Create the 'recipes' table
        self.create_table(
            """
            CREATE TABLE IF NOT EXISTS recipes(
                id INTEGER PRIMARY KEY AUTOINCREMENT, 
                name TEXT NOT NULL, 
                type TEXT NOT NULL, 
                cuisine TEXT, 
                season TEXT DEFAULT NULL,
                author TEXT,
                total_time TEXT,
                yield TEXT,
                image TEXT,
                UNIQUE (name, type, cuisine)
            );
            """
        )

        # Create the 'ingredients' table
        # section: optional heading the ingredient is grouped under (e.g. "Topping"), NULL if none
        # position: the ingredient's place in the recipe's list, so it shows in the order it was entered
        self.create_table(
            """
            CREATE TABLE IF NOT EXISTS ingredients(
                id INTEGER PRIMARY KEY AUTOINCREMENT, 
                recipe_id INTEGER NOT NULL, 
                section TEXT DEFAULT NULL,
                position INTEGER NOT NULL DEFAULT 0,
                ingredient_name TEXT NOT NULL, 
                measurement TEXT,
                FOREIGN KEY (recipe_id) REFERENCES recipes (id) ON DELETE CASCADE
            );
            """
        )
        

        # Create the 'instructions' table
        self.create_table(
            """
            CREATE TABLE IF NOT EXISTS instructions(
                id INTEGER PRIMARY KEY AUTOINCREMENT, 
                recipe_id INTEGER NOT NULL, 
                step_number INTEGER NOT NULL, 
                instruction TEXT NOT NULL, 
                UNIQUE (recipe_id, step_number),
                FOREIGN KEY (recipe_id) REFERENCES recipes (id) ON DELETE CASCADE
            );
            """
        )


        # Create the 'connections' table (links an ingredient to the step that uses it)
        self.create_table(
            """
            CREATE TABLE IF NOT EXISTS connections(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recipe_id INTEGER,
                step_number INTEGER,
                ingredient_id INTEGER,
                FOREIGN KEY (recipe_id) REFERENCES recipes (id) ON DELETE CASCADE,
                FOREIGN KEY (recipe_id, step_number) REFERENCES instructions (recipe_id, step_number) ON DELETE CASCADE,
                FOREIGN KEY (ingredient_id) REFERENCES ingredients (id) ON DELETE CASCADE
            );
            """
        )

        # Bring a database made by an older version up to date
        upgrade_schema(self.conn)


   # Method to establish a connection to the SQLite database
    def create_connection(self): 
        try:
            # Establish the connection
            conn = sqlite3.connect(self.recipe_database)
        
            # Enable foreign key constraints
            conn.execute("PRAGMA foreign_keys = ON;")
            return conn
        except Error as e:
            print(f"Error connecting to the database: {e}")
            return None
        

    # Method to execute a SQL command to create a new table (if doesn't exist)
    def create_table(self, create_table_sql):
        try:
            c = self.conn.cursor()
            c.execute(create_table_sql)
        except Error as e:
            print(e)

    # Method to insert a new recipe into the recipes table
    def add_data(self, data):
        sql = "INSERT INTO recipes(name, type, cuisine, season, author, total_time) VALUES(?,?,?,?,?,?);"
        cur = self.conn.cursor() 
        cur.execute(sql, data) 
        self.conn.commit() 
        return cur.lastrowid 
    
    # Method to add a new ingredient for a recipe in the 'ingredients' table
    # Returns the new ingredient's id
    def add_ingredient(self, recipe_id, ingredient_name, measurement, section=None, position=0):
        sql = "INSERT INTO ingredients(recipe_id, section, position, ingredient_name, measurement) VALUES(?, ?, ?, ?, ?);"
        try:
            cur = self.conn.cursor()
            cur.execute(sql, (recipe_id, section, position, ingredient_name, measurement))
            self.conn.commit()
            return cur.lastrowid
        except sqlite3.IntegrityError as e:
            print(f"Error adding ingredient: {e}")

    # Method to add an instruction step for a recipe in the 'instructions' table
    def add_instruction(self, recipe_id, step_number, instruction):
        sql = "INSERT INTO instructions(recipe_id, step_number, instruction) VALUES(?, ?, ?);"
        try:
            cur = self.conn.cursor()
            cur.execute(sql, (recipe_id, step_number, instruction))
            self.conn.commit()
        except sqlite3.IntegrityError as e:
            print(f"Error adding instruction: {e}")
    

    # Method to retrieve all records from the recipes table
    def get_recipe_with_details(self, recipe_id):
        # Fetch recipe basic information
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,))
        recipe = cur.fetchone()

        # Fetch ingredients for the recipe
        cur.execute("SELECT section, ingredient_name, measurement FROM ingredients WHERE recipe_id = ? ORDER BY position, id", (recipe_id,))
        ingredients = cur.fetchall()

        # Fetch instructions for the recipe
        cur.execute("SELECT step_number, instruction FROM instructions WHERE recipe_id = ? ORDER BY step_number", (recipe_id,))
        instructions = cur.fetchall()

        # Fetch connections (linking ingredients and instructions)
        cur.execute("""
        SELECT c.step_number, ing.ingredient_name, ing.measurement
        FROM connections c
        INNER JOIN ingredients ing ON c.ingredient_id = ing.id
        WHERE c.recipe_id = ?
        """, (recipe_id,))
        connections = cur.fetchall()

        # Structure and return all details
        return {
            "recipe": recipe,
            "ingredients": ingredients,
            "instructions": instructions,
            "connections": connections
        }
    

    # Method to delete a recipe & its associated data using cascading deletes
    def delete_recipe(self, recipe_id):
        try:
            sql = "DELETE FROM recipes WHERE id = ?"
            cur = self.conn.cursor()
            cur.execute(sql, (recipe_id,))
            self.conn.commit()
            if cur.rowcount == 0:
                print(f"No recipe found with ID {recipe_id}.")
            else:
                print(f"Recipe with ID {recipe_id} deleted successfully.")
        except sqlite3.Error as e:
            print(f"Error deleting recipe: {e}")



    # Updates recipe details
    def update_recipe(self, recipe_id, data):
        sql = """
        UPDATE recipes
        SET name = ?, type = ?, cuisine = ?, season = ?, author = ?, total_time = ?
        WHERE id = ?
        """
        try:
            cur = self.conn.cursor()
            cur.execute(sql, (*data, recipe_id))
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"Error updating recipe: {e}")



