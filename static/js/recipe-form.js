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
            <input type="hidden" name="row_kind[]" value="ingredient">
            <input type="text" class="field-input" name="measurement[]" placeholder="e.g., 1 cup" aria-label="Amount" required>
            <input type="text" class="field-input" name="ingredient_name[]" placeholder="e.g., Flour" aria-label="Ingredient" required>
            ${removeButton}
        `;
        document.getElementById('ingredients-container').appendChild(row);
        row.querySelector('input').focus();
    });

    // Add a section heading (e.g. "Topping") that groups the ingredients below it
    document.getElementById('add-section').addEventListener('click', function() {
        const row = document.createElement('div');
        row.className = 'section-row';
        row.innerHTML = `
            <input type="hidden" name="row_kind[]" value="section">
            <input type="hidden" name="measurement[]" value="">
            <input type="text" class="field-input section-input" name="ingredient_name[]" placeholder="Section, e.g., Topping" aria-label="Section name" required>
            <div class="section-move">
                <button type="button" class="btn-text move-row" data-dir="up" aria-label="Move section up" title="Move up">&uarr;</button>
                <button type="button" class="btn-text move-row" data-dir="down" aria-label="Move section down" title="Move down">&darr;</button>
            </div>
            ${removeButton}
        `;
        const container = document.getElementById('ingredients-container');
        // The first section usually names the ingredients already in the list, so it goes on top
        if (container.querySelector('.section-row')) {
            container.appendChild(row);
        } else {
            container.prepend(row);
        }
        row.querySelector('.section-input').focus();
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

    // Remove a row, or move a section heading up or down past one ingredient (works for rows added later too)
    form.addEventListener('click', function(event) {
        const button = event.target.closest('button');
        if (!button) return;
        if (button.classList.contains('remove-row')) {
            button.closest('.ingredient-row, .section-row, .instruction-row').remove();
        } else if (button.classList.contains('move-row')) {
            const row = button.closest('.section-row');
            if (button.dataset.dir === 'up' && row.previousElementSibling) {
                row.previousElementSibling.before(row);
            } else if (button.dataset.dir === 'down' && row.nextElementSibling) {
                row.nextElementSibling.after(row);
            }
            button.focus();
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
