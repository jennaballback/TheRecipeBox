# The Recipe Box

A personal recipe management website built with Flask and SQLite. Add, browse, search, filter, and edit your own recipes, complete with photos, ingredients, step-by-step instructions, and seasonal organization.

Features
- Add recipes with name, type, cuisine, season, author, total time, yield, ingredients, instructions, and a photo
- Category pages for Breakfast, Lunch, Dinner, and Dessert
- Search recipes by name, type, or cuisine
- Filter by cuisine or season via a sidebar menu that slides in from the side
- Homepage highlights, including a "Latest Recipes" grid and a seasonal "favorites" section that automatically updates based on the current month

Tech Stack
- Backend: Python, Flask
- Database: SQLite
- Frontend: HTML, CSS, JavaScript, Bootstrap 5

Database Schema
- recipes: id, name, type, cuisine, season, author, total_time, yield, image
- ingredients: id, recipe_id, ingredient_name, measurement
- instructions: id, recipe_id, step_number, instruction
- connections: link specific ingredients to specific instruction steps
