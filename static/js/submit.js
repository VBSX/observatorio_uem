document.addEventListener('DOMContentLoaded', () => {
    const localSelect = document.getElementById('{{ form.local.id }}');
    const outroLocalContainer = document.getElementById('outro-local-container');
    const outroLocalInput = document.getElementById('{{ form.outro_local_texto.id }}');

    function toggleOutroLocal() {
        if (localSelect.value === 'Outro Local / Não Listado') {
            outroLocalContainer.style.display = 'block';
            outroLocalInput.required = true;
        } else {
            outroLocalContainer.style.display = 'none';
            outroLocalInput.required = false;
        }
    }

    localSelect.addEventListener('change', toggleOutroLocal);
    
    toggleOutroLocal();
    updateCounter('{{ form.titulo.id }}', 100);
    updateCounter('{{ form.descricao.id }}', 2000);

    // === INÍCIO: JAVASCRIPT PARA ATIVAR O CARREGAMENTO ===
    const form = document.getElementById('relato-form');
    const submitButton = form.querySelector('.btn-submit');
    const loadingOverlay = document.getElementById('loading-overlay');

    form.addEventListener('submit', function() {
        // Desabilita o botão e muda o texto
        submitButton.disabled = true;
        submitButton.value = 'Enviando...';

        // Mostra o overlay de carregamento
        loadingOverlay.classList.add('visible');
    });
    // === FIM: JAVASCRIPT PARA ATIVAR O CARREGAMENTO ===
});

function updateCounter(fieldId, maxLength) {
    const field = document.getElementById(fieldId);
    const counter = document.getElementById(fieldId + '-counter');
    if (field && counter) {
        const remaining = maxLength - field.value.length;
        counter.textContent = remaining;
        counter.style.color = remaining < 20 ? (remaining < 0 ? '#ff0000' : '#ffc107') : '#aaa';
    }
}