# The Recipe Box

A collection of all the recipes we have found and use as a family.

The "recipe" table has attributes of Name, Type, Cuisine, Season, Author, Total Time, Yield, and an Image.
- Type includes Breakfast, Lunch, Dinner, Dessert, etc.
- Cuisine includes Italian, American, Mexican, etc.
- Season (if applicable) includes Autumn, Winter, Spring, and Summer.

The 'ingredients' table and 'instructions' table are children of the parent table 'recipe'.

The 'ingredients' table has attributes of Ingredients ID, Recipe ID, Ingredient Name, and Measurements.
- Ingredients ID is the primary key.
- Recipe ID is a unique number that establishes a connection to the 'recipe' table.

The 'instructions' table has attributes of Instructions ID, Recipe ID, Step Number, and Instructions.
- Instructions ID is the primary key.
- Recipe ID is a unique number that establishes a connection to the 'recipe' table.
- Step Number tracks the numerical order of the instructions.

The 'connections' table is a junction table designed to combine information from other tables.
It references:
- A specific recipe (recipe_id).
- A specific step in the instructions (step_number).
- A specific ingredient (ingredient_name).

The 'connections' table has attributes of Connections ID, Measurement, Recipe ID, Step Number, and Ingredient Name.
- Connections ID is the primary key.
- Recipe ID, Step Number, and Ingredient Name are foreign keys that make the connection between all the tables. 
