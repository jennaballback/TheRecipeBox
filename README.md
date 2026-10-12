# The Recipe Box

A personal recipe management website built with Flask and SQLite. Add, browse, search, filter, and edit your own recipes, complete with photos, ingredients, step-by-step instructions, and seasonal organization.


## Features

- **Add and edit recipes** with name, type, cuisine, season, author, total time, yield, photo, ingredients and instructions. Ingredients can be grouped under section headings such as "Crust" or "Topping".
- **Import from a link.** Paste a recipe URL and the app reads the page's schema.org Recipe data (JSON-LD), converts ISO 8601 durations like `PT1H15M` into readable times, and splits each ingredient line into a measurement and a name. Ingredient sections are kept for Tasty Recipes, WP Recipe Maker and Mediavine Create recipe cards.
- **Categories:** Breakfast, Lunch, Dinner, Dessert and Sides, each with its own page.
- **Search** by name, type or cuisine, and **filter** by cuisine or season from the side menu.
- **Home page** with a "Latest Recipes" grid and a seasonal favorites section that follows the current month.
- **Recipe page** with a checklist-style ingredient list, numbered steps and a print-friendly layout.
- **Delete with confirmation.** A popup asks before deleting; the recipe's 

Tech Stack
- Backend: Python, Flask
- Database: SQLite
- Frontend: HTML, CSS, JavaScript, Bootstrap 5

Database Schema
- recipes: id, name, type, cuisine, season, author, total_time, yield, image
- ingredients: id, recipe_id, section, position, ingredient_name, measurement (section is an optional heading such as "Topping"; position keeps the list in order)
- instructions: id, recipe_id, step_number, instruction
- connections: link specific ingredients (by ingredient id) to specific instruction steps
