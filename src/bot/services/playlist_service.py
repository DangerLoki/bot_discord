import os
import json
import asyncio
from datetime import datetime

import discord

from src.logger import get_logger
from src.bot.utils import extrair_video_id, GeoBlockedError

logger = get_logger(__name__)


class PlaylistService:
    """Serviço de gerenciamento da playlist (CRUD + adição + navegação)."""

    def __init__(self, json_playlist_path: str):
        self.json_playlist = json_playlist_path

    # =====================================================================
    # Persistência
    # =====================================================================

    def carregar_playlist(self) -> list:
        if not os.path.exists(self.json_playlist):
            return []
        try:
            with open(self.json_playlist, 'r', encoding='utf-8') as f:
                conteudo = f.read().strip()
                return json.loads(conteudo) if conteudo else []
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def salvar_playlist(self, playlist: list) -> None:
        os.makedirs(os.path.dirname(self.json_playlist), exist_ok=True)
        with open(self.json_playlist, 'w', encoding='utf-8') as f:
            json.dump(playlist, f, ensure_ascii=False, indent=2)

    # =====================================================================
    # Adição de vídeos
    # =====================================================================

    async def criar_entrada_video(self, video_id: str, url: str, info_video: dict, user: str) -> dict:
        """Cria registro de vídeo para adicionar à playlist."""
        embed_url = f'https://www.youtube.com/watch?v={video_id}'
        thumbnail_url = f'https://img.youtube.com/vi/{video_id}/hqdefault.jpg'
        
        return {
            'video_id': video_id,
            'titulo': info_video['titulo'] if info_video else None,
            'duracao': info_video['duracao'] if info_video else None,
            'duracao_formatada': info_video['duracao_formatada'] if info_video else None,
            'canal': info_video['canal'] if info_video else None,
            'embed_url': embed_url,
            'thumbnail_url': thumbnail_url,
            'adicionado_por': str(user),
            'data_adicionado': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'url': url,
            'posicao': 0,  # Será atualizado ao adicionar
            'tocado': False,
        }

    def video_existe_na_playlist(self, video_id: str) -> bool:
        """Verifica se vídeo já está na playlist."""
        playlist = self.carregar_playlist()
        return any(item['video_id'] == video_id for item in playlist)

    def adicionar_video_a_playlist(self, video_entry: dict) -> None:
        """Adiciona vídeo criado à playlist."""
        playlist = self.carregar_playlist()
        video_entry['posicao'] = len(playlist) + 1
        playlist.append(video_entry)
        self.salvar_playlist(playlist)

    def adicionar_videos_em_lote(self, videos: list, user: str) -> tuple[int, int]:
        """Adiciona múltiplos vídeos e retorna (adicionados, duplicados)."""
        playlist = self.carregar_playlist()
        ids_existentes = {v['video_id'] for v in playlist}
        
        adicionados = 0
        duplicados = 0
        novos_indices = []
        
        for video in videos:
            if video['video_id'] in ids_existentes:
                duplicados += 1
                continue
            
            playlist.append({
                'video_id': video['video_id'],
                'titulo': video['titulo'],
                'duracao': video['duracao'],
                'duracao_formatada': video['duracao_formatada'],
                'canal': video['canal'],
                'embed_url': video['embed_url'],
                'thumbnail_url': video['thumbnail_url'],
                'adicionado_por': str(user),
                'data_adicionado': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'url': video['embed_url'],
                'posicao': len(playlist) + 1,
                'tocado': False,
            })
            novos_indices.append(len(playlist) - 1)
            ids_existentes.add(video['video_id'])
            adicionados += 1
        
        self.salvar_playlist(playlist)
        return adicionados, duplicados, novos_indices

    # =====================================================================
    # Remoção
    # =====================================================================

    def remover_video_por_indice(self, index: int, is_shuffle: bool = False, 
                                shuffle_playlist: list = None) -> dict:
        """Remove vídeo por índice. Retorna dict com dados do vídeo removido."""
        playlist = self.carregar_playlist()
        
        if index < 0 or index >= len(playlist):
            return None
        
        video = playlist.pop(index)
        
        # Atualiza posições
        for i, v in enumerate(playlist):
            v['posicao'] = i + 1
        
        # Atualiza shuffle se ativo
        if is_shuffle and shuffle_playlist:
            shuffle_playlist = [pos if pos < index else pos - 1 for pos in shuffle_playlist if pos != index]
        
        self.salvar_playlist(playlist)
        return video, shuffle_playlist if is_shuffle else None

    def encontrar_video(self, entrada: str, playlist: list = None) -> tuple[int, dict] | None:
        """Encontra vídeo por posição ou ID. Retorna (index, video) ou None."""
        if not playlist:
            playlist = self.carregar_playlist()
        
        if entrada.isdigit():
            index = int(entrada) - 1
            if 0 <= index < len(playlist):
                return index, playlist[index]
        else:
            video_id = extrair_video_id(entrada) or entrada.strip()
            for i, v in enumerate(playlist):
                if v.get('video_id') == video_id:
                    return i, v
        
        return None

    # =====================================================================
    # Reordenação
    # =====================================================================

    def promover_video(self, index_video: int, playlist_index: int, 
                      is_shuffle: bool = False, shuffle_playlist: list = None,
                      shuffle_index: int = 0) -> tuple[dict, int, list, int]:
        """Promove vídeo para próxima posição.
        Retorna (embed_data, novo_playlist_index, novo_shuffle_playlist, novo_shuffle_index)
        """
        playlist = self.carregar_playlist()
        
        if index_video == playlist_index:
            return None  # Já está tocando
        
        video = playlist[index_video]
        
        if is_shuffle and shuffle_playlist:
            # No modo shuffle
            current_shuffle_pos = next((i for i, pos in enumerate(shuffle_playlist) if pos == index_video), None)
            if current_shuffle_pos is None:
                return None
            
            next_shuffle_pos = (shuffle_index + 1) % len(shuffle_playlist)
            
            if current_shuffle_pos != next_shuffle_pos:
                shuffle_playlist.pop(current_shuffle_pos)
                shuffle_playlist.insert(next_shuffle_pos, index_video)
            
            nova_pos = next_shuffle_pos + 1
            return video, playlist_index, shuffle_playlist, shuffle_index, nova_pos
        else:
            # Modo normal
            next_index = (playlist_index + 1) % len(playlist)
            
            if index_video != next_index:
                playlist.pop(index_video)
                if index_video < playlist_index:
                    playlist_index -= 1
                next_pos = playlist_index + 1
                playlist.insert(next_pos, video)
                for i, v in enumerate(playlist):
                    v['posicao'] = i + 1
            else:
                next_pos = next_index + 1
            
            self.salvar_playlist(playlist)
            return video, playlist_index, None, 0, next_pos

    # =====================================================================
    # Limpeza
    # =====================================================================

    def limpar_playlist(self) -> int:
        """Limpa a playlist e retorna total removido."""
        playlist = self.carregar_playlist()
        total = len(playlist)
        self.salvar_playlist([])
        return total
