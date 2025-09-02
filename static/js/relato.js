function updateCounter(fieldId, maxLength) {
    const field = document.getElementById(fieldId);
    const counter = document.getElementById(fieldId + '-counter');
    if (field && counter) {
        const remaining = maxLength - field.value.length;
        counter.textContent = remaining;
        counter.style.color = remaining < 20 ? (remaining < 0 ? '#ff0000' : '#ffc107') : '#aaa';
    }
}

document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('texto')) {
        updateCounter('texto', 1000);
    }

    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
    if (!csrfToken) {
        console.error("ERRO CRÍTICO: Meta tag CSRF 'csrf-token' não encontrada no <head>.");
    }

    const voteSection = document.querySelector('.vote-section');
    if (voteSection) {
        voteSection.addEventListener('click', async (e) => {
            const button = e.target.closest('.btn-vote');
            if (!button || button.disabled) return;

            const tipoVoto = button.dataset.voto;
            const messageEl = document.getElementById(tipoVoto === 'witness' ? 'witness-message' : 'vote-message');
            const relatoId = voteSection.dataset.relatoId;
            const endpoint = (tipoVoto === 'acredito' || tipoVoto === 'cetico') 
                            ? `/vote/${relatoId}/${tipoVoto}` 
                            : `/witness/${relatoId}`;

            const buttonsToDisable = [];
            if (tipoVoto === 'acredito' || tipoVoto === 'cetico') {
                buttonsToDisable.push(voteSection.querySelector('.btn-vote.acredito'));
                buttonsToDisable.push(voteSection.querySelector('.btn-vote.cetico'));
            } else if (tipoVoto === 'witness') {
                buttonsToDisable.push(voteSection.querySelector('.btn-vote.witness'));
            }

            buttonsToDisable.forEach(btn => { if(btn) btn.disabled = true; });

            try {
                const response = await fetch(endpoint, { 
                    method: 'POST',
                    headers: { 'X-CSRFToken': csrfToken }
                });
                const data = await response.json();

                if (messageEl) {
                    messageEl.textContent = data.message;
                    messageEl.style.color = data.success ? 'green' : 'red';
                }   

                if (data.success) {
                    if (data.votos_acredito !== undefined) document.getElementById('votos-acredito').textContent = data.votos_acredito;
                    if (data.votos_cetico !== undefined) document.getElementById('votos-cetico').textContent = data.votos_cetico;
                    if (data.votos_testemunha !== undefined) document.getElementById('votos-testemunha').textContent = data.votos_testemunha;
                } else {
                    buttonsToDisable.forEach(btn => { if(btn) btn.disabled = false; });
                }
            } catch (error) {
                console.error("Erro na requisição de voto:", error);
                if (messageEl) {
                    messageEl.textContent = 'Falha na comunicação com o servidor.';
                    messageEl.style.color = 'red';
                }
                buttonsToDisable.forEach(btn => { if(btn) btn.disabled = false; });
            }
        });
    }
    
    // --- LÓGICA DE LIKE/UNLIKE ATUALIZADA ---
    document.querySelectorAll('.like-icon').forEach(icon => {
        icon.addEventListener('click', async function likeToggleHandler(e) {
            const likeIcon = e.target;
            const commentContainer = likeIcon.closest('.like-container');
            const commentId = commentContainer.dataset.commentId;

            if (!commentId || !csrfToken) {
                console.error("Faltando ID do comentário ou token CSRF.");
                return;
            }

            // Previne cliques múltiplos enquanto a requisição está em andamento
            if (likeIcon.classList.contains('processing')) return;
            likeIcon.classList.add('processing');

            try {
                const response = await fetch(`/like_comment/${commentId}`, {
                    method: 'POST',
                    headers: { 'X-CSRFToken': csrfToken }
                });
                const data = await response.json();

                if (response.ok && data.success) {
                    const likeCountSpan = commentContainer.querySelector('.like-count');
                    if (likeCountSpan) {
                        likeCountSpan.textContent = data.contagens;
                    }

                    // Alterna o estado do ícone com base na resposta do servidor
                    if (data.action === 'liked') {
                        likeIcon.src = likeIcon.src.replace('ghost_sem_like.png', 'ghost.png');
                        likeIcon.classList.remove('not-liked');
                        likeIcon.classList.add('liked');
                    } else if (data.action === 'unliked') {
                        likeIcon.src = likeIcon.src.replace('ghost.png', 'ghost_sem_like.png');
                        likeIcon.classList.remove('liked');
                        likeIcon.classList.add('not-liked');
                    }
                } else {
                    alert(data.message || 'Não foi possível registrar sua ação.');
                }
            } catch (error) {
                console.error("Erro na requisição de like/unlike:", error);
                alert('Falha na comunicação ao tentar interagir com o comentário.');
            } finally {
                // Libera o ícone para o próximo clique
                likeIcon.classList.remove('processing');
            }
        });
    });
});