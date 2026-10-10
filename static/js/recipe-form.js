// Shared behavior for the Add and Edit recipe forms.
(function() {
    'use strict';

    const form = document.querySelector('.recipe-form');
    if (!form) return;

    const removeButton = '<button type="button" class="btn-text remove-row">Remove</button>';

    function growTextarea(el) {
        el.style.height = 'auto';
        el.style.height = el.scrollHeight + 'px';
    }

    // Add ingredient row
    document.getElementById('add-ingredient').addEventListener('click', function() {
        const row = document.createElement('div');
        row.className = 'ingredient-row';
        row.innerHTML = `
            <input type="text" class="field-input" name="measurement[]" placeholder="e.g., 1 cup" aria-label="Amount" required>
            <input type="text" class="field-input" name="ingredient_name[]" placeholder="e.g., Flour" aria-label="Ingredient" required>
            ${removeButton}
        `;
        document.getElementById('ingredients-container').appendChild(row);
        row.querySelector('input').focus();
    });

    // Add instruction row
    document.getElementById('add-instruction').addEventListener('click', function() {
        const row = document.createElement('div');
        row.className = 'instruction-row';
        row.innerHTML = `
            <textarea class="field-input auto-grow" name="instruction[]" placeholder="e.g., Mix all ingredients" rows="1" aria-label="Step" required></textarea>
            ${removeButton}
        `;
        document.getElementById('instructions-container').appendChild(row);
        row.querySelector('textarea').focus();
    });

    // Remove an ingredient or instruction (works for rows added later too)
    form.addEventListener('click', function(event) {
        if (event.target.classList.contains('remove-row')) {
            event.target.closest('.ingredient-row, .instruction-row').remove();
        }
    });

    // Auto-grow textareas as text is typed, and pre-filled ones on load
    form.addEventListener('input', function(event) {
        if (event.target.classList.contains('auto-grow')) growTextarea(event.target);
    });
    form.querySelectorAll('textarea.auto-grow').forEach(growTextarea);

    // Photo preview (choosing a new photo replaces the current or imported one)
    document.getElementById('photo').addEventListener('change', function(event) {
        const preview = document.getElementById('photoPreview');
        preview.innerHTML = '';
        const file = event.target.files[0];
        if (file) {
            const img = document.createElement('img');
            img.src = URL.createObjectURL(file);
            img.alt = 'New photo';
            preview.appendChild(img);
        }
    });

    // Highlight missing fields instead of submitting
    form.addEventListener('submit', function(event) {
        if (!form.checkValidity()) {
            event.preventDefault();
            event.stopPropagation();
            const firstInvalid = form.querySelector(':invalid');
            if (firstInvalid) firstInvalid.focus();
        }
        form.classList.add('was-validated');
    });
})();
