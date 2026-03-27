import logging
import os
from src.logger import get_logger

logger = get_logger(__name__)

from flask import Flask, render_template, jsonify, request
import json
import os

app = Flask(__name__)

# Caminho para o arquivo da playlist
PLAYLIST_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'playlist.json')

# Índice do vídeo atual (variável global)
video_atual_index = 0

# ===================================================
# Funções auxiliares para manipulação da playlist
# ===================================================
def carregar_playlist():
    """Carrega a playlist do arquivo JSON"""
    if not os.path.exists(PLAYLIST_PATH):
        return []
    
    try:
        with open(PLAYLIST_PATH, 'r', encoding='utf-8') as f:
            conteudo = f.read().strip()
            if not conteudo:
                return []
            return json.loads(conteudo)
    except (json.JSONDecodeError, FileNotFoundError):
        return []

def salvar_playlist(playlist):
    """Salva a playlist no arquivo JSON"""
    os.makedirs(os.path.dirname(PLAYLIST_PATH), exist_ok=True)
    with open(PLAYLIST_PATH, 'w', encoding='utf-8') as f:
        json.dump(playlist, f, ensure_ascii=False, indent=2)

# ===================================================
# Rotas do Flask
# ===================================================
@app.route('/')
def index():
    """Página principal com o player"""
    videos = carregar_playlist()
    return render_template('player.html', videos=videos)

@app.route('/api/playlist')
def api_playlist():
    """API para obter a playlist em JSON"""
    videos = carregar_playlist()
    return jsonify(videos)

@app.route('/api/playlist/remove/<video_id>', methods=['DELETE'])
def remover_video(video_id):
    """Remove um vídeo da playlist"""
    global video_atual_index
    playlist = carregar_playlist()
    
    if not playlist:
        return jsonify({'success': False, 'message': 'Playlist vazia'})
    
    # Encontra o índice do vídeo a ser removido
    index_removido = None
    for i, video in enumerate(playlist):
        if video.get('video_id') == video_id:
            index_removido = i
            break
    
    if index_removido is None:
        return jsonify({'success': False, 'message': 'Vídeo não encontrado'})
    
    # Verifica se está removendo o vídeo atual
    removendo_atual = (index_removido == video_atual_index)
    
    # Remove o vídeo
    video_removido = playlist.pop(index_removido)
    
    # Atualiza as posições dos vídeos restantes
    for i, video in enumerate(playlist):
        video['posicao'] = i + 1
    
    salvar_playlist(playlist)
    
    logger.info(f'[REMOVE] vídeo {video_id} removido — {len(playlist)} restantes')

    # Ajusta o índice atual
    if len(playlist) == 0:
        video_atual_index = 0
        return jsonify({
            'success': True,
            'message': 'Vídeo removido. Playlist vazia.',
            'video_removido': video_removido,
            'playlist_vazia': True,
            'index': 0,
            'total': 0,
            'proximo_video': None,
            'removeu_atual': removendo_atual
        })
    
    # Se removeu um vídeo antes do atual, ajusta o índice
    if index_removido < video_atual_index:
        video_atual_index -= 1
    # Se removeu o vídeo atual, mantém o índice (agora aponta para o próximo)
    elif removendo_atual:
        # Se era o último, volta para o primeiro
        if video_atual_index >= len(playlist):
            video_atual_index = 0
    
    return jsonify({
        'success': True,
        'message': 'Vídeo removido com sucesso',
        'video_removido': video_removido,
        'playlist_vazia': False,
        'index': video_atual_index,
        'total': len(playlist),
        'proximo_video': playlist[video_atual_index],
        'removeu_atual': removendo_atual
    })

@app.route('/api/playlist/atual', methods=['GET'])
def video_atual():
    """Retorna o vídeo atual sem avançar"""
    global video_atual_index
    playlist = carregar_playlist()
    
    if not playlist:
        return jsonify({'success': False, 'message': 'Playlist vazia', 'video': None})
    
    # Garante que o índice está dentro dos limites
    if video_atual_index >= len(playlist):
        video_atual_index = 0
        
    return jsonify({
        'success': True, 
        'video': playlist[video_atual_index],
        'index': video_atual_index,
        'total': len(playlist)
    })

@app.route('/api/playlist/set/<int:index>', methods=['POST'])
def definir_video(index):
    """Define qual vídeo está tocando atualmente"""
    global video_atual_index
    playlist = carregar_playlist()
    
    if not playlist:
        return jsonify({'success': False, 'message': 'Playlist vazia'})
    
    if index < 0 or index >= len(playlist):
        return jsonify({'success': False, 'message': 'Índice inválido'})
    
    video_atual_index = index
    
    return jsonify({
        'success': True,
        'video': playlist[video_atual_index],
        'index': video_atual_index,
        'total': len(playlist)
    })

@app.route('/api/playlist/skip', methods=['POST'])
def proximo_video():
    """Avança para o próximo vídeo"""
    global video_atual_index
    playlist = carregar_playlist()
    
    if not playlist:
        return jsonify({'success': False, 'message': 'Playlist vazia', 'video': None})
    
    # Avança para o próximo
    video_atual_index += 1
    
    # Loop: volta para o início se chegou no fim
    if video_atual_index >= len(playlist):
        video_atual_index = 0
    
    logger.info(f'[SKIP] → índice {video_atual_index}: {playlist[video_atual_index].get("titulo", "?")}')

    return jsonify({
        'success': True, 
        'video': playlist[video_atual_index],
        'index': video_atual_index,
        'total': len(playlist)

    })

@app.route('/api/playlist/previous', methods=['POST'])
def video_anterior():
    """Volta para o vídeo anterior"""
    global video_atual_index
    playlist = carregar_playlist()
    
    if not playlist:
        return jsonify({'success': False, 'message': 'Playlist vazia', 'video': None})
    
    # Volta para o anterior
    video_atual_index -= 1
    
    # Loop: vai para o fim se estiver no início
    if video_atual_index < 0:
        video_atual_index = len(playlist) - 1
    
    return jsonify({
        'success': True, 
        'video': playlist[video_atual_index],
        'index': video_atual_index,
        'total': len(playlist)
    })

@app.route('/api/playlist/clear', methods=['DELETE'])
def limpar_playlist():
    """Remove todos os vídeos da playlist"""
    global video_atual_index
    salvar_playlist([])
    video_atual_index = 0
    logger.info('[CLEAR] Playlist limpa via interface web')
    return jsonify({'success': True, 'message': 'Playlist limpa com sucesso'})

@app.route('/api/playlist/promote/<video_id>', methods=['POST'])
def promover_video(video_id):
    """Move um vídeo para ser o próximo a tocar"""
    global video_atual_index
    playlist = carregar_playlist()

    if not playlist:
        return jsonify({'success': False, 'message': 'Playlist vazia'})

    index_video = next((i for i, v in enumerate(playlist) if v.get('video_id') == video_id), None)

    if index_video is None:
        return jsonify({'success': False, 'message': 'Vídeo não encontrado'})

    if index_video == video_atual_index:
        return jsonify({'success': False, 'message': 'Este vídeo já está tocando'})

    next_index = video_atual_index + 1

    # Já é o próximo
    if index_video == next_index:
        return jsonify({'success': True, 'message': 'Vídeo já é o próximo', 'video': playlist[index_video], 'current_index': video_atual_index})

    # Remove da posição atual
    video = playlist.pop(index_video)

    # Ajusta o índice atual se o vídeo estava antes dele
    if index_video < video_atual_index:
        video_atual_index -= 1

    # Insere logo após o atual
    next_pos = video_atual_index + 1
    playlist.insert(next_pos, video)

    # Atualiza posições
    for i, v in enumerate(playlist):
        v['posicao'] = i + 1

    salvar_playlist(playlist)
    logger.info(f'[PROMOTE] {video_id} ("{video.get("titulo", "?")}") movido para posição {next_pos + 1}')

    return jsonify({
        'success': True,
        'message': f'Vídeo promovido para a próxima posição!',
        'video': video,
        'nova_posicao': next_pos + 1,
        'current_index': video_atual_index
    })

# ===================================================
# Função para iniciar o servidor Flask
# ===================================================
def iniciar_servidor(host='0.0.0.0', port=5000, debug=False):
    """Inicia o servidor Flask"""
    app.run(host=host, port=port, debug=debug, use_reloader=False)

if __name__ == '__main__':
    iniciar_servidor(debug=True)