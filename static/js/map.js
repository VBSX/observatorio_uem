
// Coordenadas do centro do campus da UEM
const uemCenter = [-23.407, -51.938];

// Limites do mapa
const southWest = L.latLng(-23.414, -51.946);
const northEast = L.latLng(-23.400, -51.931);
const bounds = L.latLngBounds(southWest, northEast);

// Inicializa o mapa
const map = L.map('map', {
    center: uemCenter,
    zoom: 15,
    maxBounds: bounds,
    minZoom: 15
});
map.fitBounds(bounds);

// Adiciona o "tile layer"
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '© <a href="http://www.openstreetmap.org/copyright">OpenStreetMap</a>'
}).addTo(map);

// Ícone personalizado
const ghostIcon = L.icon({
    iconUrl: 'https://img.icons8.com/ios-filled/50/8A2BE2/ghost.png',
    iconSize: [35, 35],
    iconAnchor: [17, 35],
    popupAnchor: [0, -35]
});

// Função para criar o conteúdo do Popup com navegação
function createPopupContent(local, marker) {
    let currentIndex = 0;
    const relatos = local.relatos;

    function updatePopup() {
        const relato = relatos[currentIndex];
        const total = relatos.length;
        
        let navigationHtml = '';
        if (total > 1) {
            navigationHtml = `
                <div class="popup-nav">
                    <button class="nav-btn prev" ${currentIndex === 0 ? 'disabled' : ''}>&larr;</button>
                    <span>Relato ${currentIndex + 1} de ${total}</span>
                    <button class="nav-btn next" ${currentIndex === total - 1 ? 'disabled' : ''}>&rarr;</button>
                </div>
            `;
        }

        const content = `
            <div class="popup-content">
                <h4>${relato.titulo}</h4>
                <p><strong>Local:</strong> ${relato.local}</p>
                <p><strong>Categoria:</strong> ${relato.categoria}</p>
                <p><strong>Data:</strong> ${relato.criado_em}</p>
                <a href="/relato/${relato.id}" target="_blank">Ver detalhes e comentar...</a>
                ${navigationHtml}
            </div>
        `;
        
        marker.getPopup().setContent(content);
        addPopupListeners();
    }

    function addPopupListeners() {
        const popupElement = marker.getPopup().getElement();
        if (!popupElement) return;
        
        // --- INÍCIO DA CORREÇÃO ---
        // Impede que cliques dentro do conteúdo do popup fechem a janela
        const contentWrapper = popupElement.querySelector('.popup-content');
        if (contentWrapper) {
            L.DomEvent.disableClickPropagation(contentWrapper);
        }
        // --- FIM DA CORREÇÃO ---

        popupElement.querySelector('.prev')?.addEventListener('click', () => {
            if (currentIndex > 0) {
                currentIndex--;
                updatePopup();
            }
        });
        popupElement.querySelector('.next')?.addEventListener('click', () => {
            if (currentIndex < relatos.length - 1) {
                currentIndex++;
                updatePopup();
            }
        });
    }
    
    marker.on('popupopen', addPopupListeners);
    updatePopup(); // Gera o conteúdo inicial
}

// Adiciona os marcadores no mapa
if (locais_data) {
    locais_data.forEach(local => {
        const marker = L.marker([local.lat, local.lon], { icon: ghostIcon }).addTo(map);
        const popup = L.popup({ minWidth: 250 });
        marker.bindPopup(popup);
        createPopupContent(local, marker);
    });
}