// Coordenadas do centro do campus da UEM
const uemCenter = [-23.407, -51.938];

// 1. Define a ÁREA DE VISUALIZAÇÃO INICIAL (o campus)
const initialSouthWest = L.latLng(-23.408829278190915, -51.947006412057846);
const initialNorthEast = L.latLng(-23.403331898752555, -51.93086554610066);
const initialBounds = L.latLngBounds(initialSouthWest, initialNorthEast);

// 2. Define LIMITES DE NAVEGAÇÃO MAIORES (permitindo explorar os arredores)
const maxBoundsSouthWest = L.latLng(-23.45, -52.00);
const maxBoundsNorthEast = L.latLng(-23.35, -51.88);
const maxBounds = L.latLngBounds(maxBoundsSouthWest, maxBoundsNorthEast);

// Inicializa o mapa com os limites MAIORES
const map = L.map('map', {
    center: uemCenter,
    zoom: 15,
    maxBounds: maxBounds, // Define o limite máximo de pan
    minZoom: 13           // Permite diminuir mais o zoom
});

// Define a visualização inicial para focar no campus
map.fitBounds(initialBounds);

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

        // Adiciona a miniatura da imagem se ela existir
        let imageHtml = relato.imagem_url ? `<div class="popup-image-container"><img src="${relato.imagem_url}" alt="Miniatura do relato"></div>` : '';

        const content = `
            <div class="popup-content">
                ${imageHtml}
                <h4>${relato.titulo}</h4>
                <p><strong>Local:</strong> ${relato.local}</p>
                <p><strong>Categoria:</strong> ${relato.categoria}</p>
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
        
        const contentWrapper = popupElement.querySelector('.popup-content');
        if (contentWrapper) {
            L.DomEvent.disableClickPropagation(contentWrapper);
        }

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
    updatePopup();
}

// Adiciona os marcadores no mapa
if (typeof locais_data !== 'undefined' && locais_data) {
    locais_data.forEach(local => {
        const marker = L.marker([local.lat, local.lon], { icon: ghostIcon }).addTo(map);
        
        // Mantendo a versão com autoPan e padding, que é mais estável
        const popup = L.popup({ 
            minWidth: 250, 
            autoPan: true, 
            autoPanPadding: L.point(75, 75) 
        });
        marker.bindPopup(popup);
        createPopupContent(local, marker);
    });
}
