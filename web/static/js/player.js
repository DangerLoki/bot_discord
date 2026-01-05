// Variáveis globais
let currentIndex = 0;
let isShuffleMode = false;
let player = null;
let playlistData = [];

// Inicialização quando a página carregar
document.addEventListener('DOMContentLoaded', function() {
    // Adiciona event listeners aos itens já renderizados pelo servidor
    attachPlaylistEventListeners();
    
    loadPlaylist().then(() => {
        setupEventListeners();
        loadYouTubeAPI();
    });
    
    // Verifica por novos vídeos a cada 3 segundos
    setupAutoRefresh();
});

// Carrega a playlist da API
async function loadPlaylist() {
    try {
        const response = await fetch('/api/playlist');
        playlistData = await response.json();
        renderPlaylist();
        return playlistData;
    } catch (error) {
        console.error('Erro ao carregar playlist:', error);
        return [];
    }
}

// Renderiza a playlist no HTML (sem recarregar a página)
function renderPlaylist() {
    const container = document.querySelector('.playlist-container');
    if (!container) {
        console.error('Container .playlist-container não encontrado!');
        return;
    }
    
    // Limpa o container
    container.innerHTML = '';
    
    if (playlistData.length === 0) {
        container.innerHTML = `
            <div class="empty-playlist">
                <p>🎵 Nenhum vídeo na playlist</p>
                <p>Use !sr [link] no Discord para adicionar</p>
            </div>
        `;
        return;
    }
    
    // Cria cada item da playlist
    playlistData.forEach((video, index) => {
        const item = document.createElement('div');
        item.className = `playlist-item${index === currentIndex ? ' active' : ''}`;
        item.setAttribute('data-index', index);
        item.setAttribute('data-video-id', video.video_id);
        item.style.cursor = 'pointer';
        
        // Thumbnail
        const thumbnail = document.createElement('img');
        thumbnail.src = video.thumbnail || video.thumbnail_url || `https://img.youtube.com/vi/${video.video_id}/mqdefault.jpg`;
        thumbnail.alt = 'Thumbnail';
        thumbnail.className = 'video-thumbnail';
        
        // Info container
        const info = document.createElement('div');
        info.className = 'video-info';
        
        const titulo = document.createElement('p');
        titulo.className = 'video-title';
        titulo.textContent = video.titulo || 'Título desconhecido';
        
        const usuario = document.createElement('p');
        usuario.className = 'video-author';
        usuario.textContent = `Adicionado por: ${video.usuario || video.adicionado_por || 'Anônimo'}`;
        
        info.appendChild(titulo);
        info.appendChild(usuario);
        
        // Botão remover
        const removeBtn = document.createElement('button');
        removeBtn.className = 'remove-btn';
        removeBtn.setAttribute('data-video-id', video.video_id);
        removeBtn.textContent = '✕';
        
        // Monta o item
        item.appendChild(thumbnail);
        item.appendChild(info);
        item.appendChild(removeBtn);
        
        // Adiciona ao container
        container.appendChild(item);
    });
    
    // Atualiza contador
    const contador = document.querySelector('.playlist-count');
    if (contador) {
        contador.textContent = `${playlistData.length} vídeo${playlistData.length !== 1 ? 's' : ''} na fila`;
    }
    
    // Re-adiciona os event listeners após renderizar
    attachPlaylistEventListeners();
}

// Adiciona event listeners aos itens da playlist
function attachPlaylistEventListeners() {
    const container = document.querySelector('.playlist-container');
    if (!container) return;
    
    // Remove listener antigo se existir
    container.removeEventListener('click', handlePlaylistClick);
    
    // Usa event delegation - um único listener no container
    container.addEventListener('click', handlePlaylistClick);
}

// Handler separado para o clique na playlist
function handlePlaylistClick(e) {
    const target = e.target;
    
    // Verifica se clicou no botão de remover
    if (target.classList.contains('remove-btn')) {
        e.stopPropagation();
        e.preventDefault();
        const videoId = target.getAttribute('data-video-id');
        console.log('Removendo vídeo:', videoId);
        removeVideo(videoId);
        return;
    }
    
    // Encontra o playlist-item mais próximo
    const playlistItem = target.closest('.playlist-item');
    if (playlistItem) {
        const index = parseInt(playlistItem.getAttribute('data-index'));
        console.log('Clicou no item:', index);
        playVideo(index);
    }
}

// Verifica por novos vídeos automaticamente
function setupAutoRefresh() {
    setInterval(async function() {
        try {
            const response = await fetch('/api/playlist');
            const newPlaylist = await response.json();
            
            // Verifica se a playlist mudou
            const playlistMudou = JSON.stringify(newPlaylist.map(v => v.video_id)) !== 
                                  JSON.stringify(playlistData.map(v => v.video_id));
            
            if (playlistMudou) {
                const videosAntigos = playlistData.length;
                playlistData = newPlaylist;
                
                // Renderiza novamente sem recarregar
                renderPlaylist();
                
                // Notifica se adicionou vídeos novos
                if (newPlaylist.length > videosAntigos) {
                    const novosVideos = newPlaylist.length - videosAntigos;
                    showNotification(`🎵 ${novosVideos} novo${novosVideos > 1 ? 's' : ''} vídeo${novosVideos > 1 ? 's' : ''} adicionado${novosVideos > 1 ? 's' : ''}!`);
                }
                
                console.log('Playlist atualizada:', newPlaylist.length, 'vídeos');
            }
        } catch (error) {
            console.error('Erro ao verificar atualizações:', error);
        }
    }, 3000);
}

// Carrega a API do YouTube IFrame
function loadYouTubeAPI() {
    if (window.YT && window.YT.Player) {
        onYouTubeIframeAPIReady();
        return;
    }
    
    const tag = document.createElement('script');
    tag.src = 'https://www.youtube.com/iframe_api';
    const firstScriptTag = document.getElementsByTagName('script')[0];
    firstScriptTag.parentNode.insertBefore(tag, firstScriptTag);
}

// Callback chamado quando a API do YouTube está pronta
function onYouTubeIframeAPIReady() {
    console.log('YouTube API pronta');
    if (playlistData && playlistData.length > 0) {
        createYouTubePlayer(playlistData[currentIndex].video_id);
    }
}

// Cria o player do YouTube com a API oficial
function createYouTubePlayer(videoId) {
    const playerContainer = document.querySelector('.player-container');
    if (!playerContainer) {
        console.error('Container .player-container não encontrado!');
        return;
    }
    
    playerContainer.innerHTML = '<div id="youtube-player"></div>';
    
    player = new YT.Player('youtube-player', {
        width: '100%',
        height: '100%',
        videoId: videoId,
        playerVars: {
            'autoplay': 1,
            'controls': 1,
            'rel': 0,
            'modestbranding': 1
        },
        events: {
            'onReady': onPlayerReady,
            'onStateChange': onPlayerStateChange
        }
    });
}

// Quando o player estiver pronto
function onPlayerReady(event) {
    console.log('Player pronto');
    event.target.playVideo();
}

// Detecta mudança de estado do vídeo (AUTOPLAY)
function onPlayerStateChange(event) {
    if (event.data === YT.PlayerState.ENDED) {
        console.log('Vídeo terminou, tocando próximo...');
        playNext();
    }
}

function setupEventListeners() {
    // Botão Anterior
    const btnAnterior = document.getElementById('btn-anterior');
    if (btnAnterior) {
        btnAnterior.addEventListener('click', function() {
            if (playlistData.length === 0) return;
            currentIndex = (currentIndex - 1 + playlistData.length) % playlistData.length;
            playVideo(currentIndex);
        });
    }

    // Botão Próximo
    const btnProximo = document.getElementById('btn-proximo');
    if (btnProximo) {
        btnProximo.addEventListener('click', function() {
            if (playlistData.length === 0) return;
            playNext();
        });
    }

    // Botão Aleatório
    const btnShuffle = document.getElementById('btn-shuffle');
    if (btnShuffle) {
        btnShuffle.addEventListener('click', function() {
            isShuffleMode = !isShuffleMode;
            this.style.background = isShuffleMode 
                ? 'linear-gradient(135deg, #ff6b6b 0%, #ee5a24 100%)' 
                : 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)';
            showNotification(isShuffleMode ? '🔀 Modo aleatório ativado' : '🔀 Modo aleatório desativado');
        });
    }

    // Botão Atualizar
    const btnRefresh = document.getElementById('btn-refresh');
    if (btnRefresh) {
        btnRefresh.addEventListener('click', function() {
            loadPlaylist();
            showNotification('🔄 Playlist atualizada!');
        });
    }
}

function playVideo(index) {
    if (index < 0 || index >= playlistData.length) return;
    
    currentIndex = index;
    const video = playlistData[index];
    
    console.log('Tocando vídeo:', index, video.titulo);
    
    if (player && player.loadVideoById) {
        player.loadVideoById(video.video_id);
    } else {
        createYouTubePlayer(video.video_id);
    }
    
    updateActiveItem(index);
}

function playNext() {
    if (playlistData.length === 0) return;
    
    if (isShuffleMode) {
        let newIndex;
        do {
            newIndex = Math.floor(Math.random() * playlistData.length);
        } while (newIndex === currentIndex && playlistData.length > 1);
        currentIndex = newIndex;
    } else {
        currentIndex = (currentIndex + 1) % playlistData.length;
    }
    
    playVideo(currentIndex);
    showNotification(`▶️ Tocando: ${playlistData[currentIndex].titulo}`);
}

function updateActiveItem(index) {
    document.querySelectorAll('.playlist-item').forEach(function(item, i) {
        if (i === index) {
            item.classList.add('active');
        } else {
            item.classList.remove('active');
        }
    });
    
    const activeItem = document.querySelector('.playlist-item.active');
    if (activeItem) {
        activeItem.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
}

async function removeVideo(videoId) {
    try {
        const response = await fetch(`/api/playlist/remove/${videoId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            // Remove localmente e re-renderiza
            const indexRemovido = playlistData.findIndex(v => v.video_id === videoId);
            playlistData = playlistData.filter(v => v.video_id !== videoId);
            
            // Ajusta o índice atual se necessário
            if (indexRemovido < currentIndex) {
                currentIndex--;
            } else if (indexRemovido === currentIndex && playlistData.length > 0) {
                if (currentIndex >= playlistData.length) {
                    currentIndex = 0;
                }
                playVideo(currentIndex);
            }
            
            renderPlaylist();
            showNotification('✅ Vídeo removido da playlist');
        } else {
            showNotification('❌ Erro ao remover vídeo');
        }
    } catch (error) {
        console.error('Erro:', error);
        showNotification('❌ Erro ao remover vídeo');
    }
}

function showNotification(message) {
    const existing = document.querySelector('.notification');
    if (existing) existing.remove();
    
    const notification = document.createElement('div');
    notification.className = 'notification';
    notification.textContent = message;
    document.body.appendChild(notification);
    
    setTimeout(() => notification.remove(), 3000);
}