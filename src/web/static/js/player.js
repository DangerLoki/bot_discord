// Variáveis globais
let currentIndex = 0;
let isShuffleMode = false;
let player = null;
let playlistData = [];
let ultimoIndexConhecido = 0;  // Adiciona aqui

// Inicialização quando a página carregar
document.addEventListener('DOMContentLoaded', function() {
    // Adiciona event listeners aos itens já renderizados pelo servidor
    attachPlaylistEventListeners();
    
    loadPlaylist().then(() => {
        setupEventListeners();
        loadYouTubeAPI();
        
        // Sincroniza com a API ao iniciar
        sincronizarComAPI();
    });
    
    // Verifica por novos vídeos a cada 3 segundos
    setupAutoRefresh();
    
    // Verifica se alguém pulou pelo Discord a cada 2 segundos
    setupDiscordSkipListener();
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

        // Botão promover (apenas se não for o atual)
        const promoteBtn = document.createElement('button');
        promoteBtn.className = 'promote-btn';
        promoteBtn.setAttribute('data-video-id', video.video_id);
        promoteBtn.title = 'Tocar em seguida';
        promoteBtn.textContent = '\u23ed\ufe0f';

        // Monta o item
        item.appendChild(thumbnail);
        item.appendChild(info);
        if (index !== currentIndex) item.appendChild(promoteBtn);
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
        removeVideo(videoId);
        return;
    }

    // Verifica se clicou no botão de promover
    if (target.classList.contains('promote-btn')) {
        e.stopPropagation();
        e.preventDefault();
        const videoId = target.getAttribute('data-video-id');
        promoteVideo(videoId);
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

    // Botão Limpar tudo
    const btnClear = document.getElementById('btn-clear');
    if (btnClear) {
        btnClear.addEventListener('click', function() {
            if (!confirm('Tem certeza que deseja limpar toda a playlist?')) return;
            clearPlaylist();
        });
    }
}

// Limpa toda a playlist
async function clearPlaylist() {
    try {
        const response = await fetch('/api/playlist/clear', { method: 'DELETE' });
        const data = await response.json();
        if (data.success) {
            playlistData = [];
            currentIndex = 0;
            ultimoIndexConhecido = 0;
            if (player && player.stopVideo) player.stopVideo();
            renderPlaylist();
            showNotification('🗑️ Playlist limpa!');
        } else {
            showNotification('❌ ' + data.message);
        }
    } catch (e) {
        console.error('Erro ao limpar playlist:', e);
        showNotification('❌ Erro ao limpar playlist');
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
    
    // Atualiza o destaque visual
    updateActiveItem(index);
    
    // Informa a API que mudou de vídeo
    informarVideoAtual(index);
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

// Remove um vídeo da playlist
async function removeVideo(videoId, index) {
    try {
        const response = await fetch(`/api/playlist/remove/${videoId}`, {
            method: 'DELETE'
        });
        const data = await response.json();
        
        if (data.success) {
            // Atualiza a playlist local
            await loadPlaylist();
            
            if (data.playlist_vazia) {
                // Playlist ficou vazia
                currentIndex = 0;
                ultimoIndexConhecido = 0;
                if (player && player.stopVideo) {
                    player.stopVideo();
                }
                showNotification('🗑️ Playlist vazia!');
            } else {
                // Atualiza o índice com o valor da API
                currentIndex = data.index;
                ultimoIndexConhecido = data.index;
                
                // Se removeu o vídeo que estava tocando, toca o próximo
                if (data.removeu_atual) {
                    playVideo(currentIndex);
                    showNotification('🗑️ Vídeo removido! Tocando próximo...');
                } else {
                    // Apenas atualiza o destaque visual
                    updateActiveItem(currentIndex);
                    showNotification('🗑️ Vídeo removido!');
                }
            }
            
            renderPlaylist();
        } else {
            showNotification('❌ ' + data.message);
        }
    } catch (e) {
        console.error('Erro ao remover vídeo:', e);
        showNotification('❌ Erro ao remover vídeo');
    }
}
// Promove um vídeo para ser o próximo a tocar
async function promoteVideo(videoId) {
    try {
        const response = await fetch(`/api/playlist/promote/${videoId}`, { method: 'POST' });
        const data = await response.json();
        if (data.success) {
            // Atualiza os índices ANTES de recarregar para o poller não disparar um falso skip
            if (typeof data.current_index === 'number') {
                currentIndex = data.current_index;
                ultimoIndexConhecido = data.current_index;
            }
            await loadPlaylist();
            updateActiveItem(currentIndex);
            showNotification(`\u23ed\ufe0f Próximo: ${playlistData.find(v => v.video_id === videoId)?.titulo || 'Vídeo'}`);
        } else {
            showNotification('\u274c ' + data.message);
        }
    } catch (e) {
        console.error('Erro ao promover vídeo:', e);
        showNotification('\u274c Erro ao promover vídeo');
    }
}
// Atualiza o item ativo na playlist (destaque visual)
function updateActiveItem(index) {
    // Remove destaque de todos
    document.querySelectorAll('.playlist-item').forEach((item, i) => {
        item.classList.remove('active', 'playing');
    });
    
    // Adiciona destaque ao item atual
    const items = document.querySelectorAll('.playlist-item');
    if (items[index]) {
        items[index].classList.add('active', 'playing');
    }
}

// Verifica se alguém pulou pelo Discord
function setupDiscordSkipListener() {
    setInterval(async () => {
        try {
            const response = await fetch('/api/playlist/atual');
            const data = await response.json();
            
            if (data.success && data.index !== ultimoIndexConhecido) {
                console.log('Mudança detectada! De', ultimoIndexConhecido, 'para', data.index);
                ultimoIndexConhecido = data.index;
                currentIndex = data.index;
                
                // Atualiza o player e o destaque
                playVideo(data.index);
                updateActiveItem(data.index);
                showNotification('⏭️ Vídeo alterado pelo Discord!');
            }
        } catch (e) {
            console.error('Erro ao verificar vídeo atual:', e);
        }
    }, 2000);
}

// Sincroniza o índice local com a API
async function sincronizarComAPI() {
    try {
        const response = await fetch('/api/playlist/atual');
        const data = await response.json();
        
        if (data.success) {
            ultimoIndexConhecido = data.index;
            currentIndex = data.index;
            console.log('Sincronizado com API, índice:', data.index);
        }
    } catch (e) {
        console.error('Erro ao sincronizar com API:', e);
    }
}

// Informa a API quando muda de vídeo localmente
async function informarVideoAtual(index) {
    try {
        await fetch(`/api/playlist/set/${index}`, { method: 'POST' });
        ultimoIndexConhecido = index;
        console.log('API informada, novo índice:', index);
    } catch (e) {
        console.error('Erro ao informar API:', e);
    }
}