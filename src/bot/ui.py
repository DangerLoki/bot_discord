import discord
from discord.ui import View, Button


class PaginacaoPlaylist(View):
    def __init__(self, playlist, titulo="🎵 Playlist de Vídeos", itens_por_pagina=10, timeout=60):
        super().__init__(timeout=timeout)
        self.playlist = playlist
        self.titulo = titulo
        self.itens_por_pagina = itens_por_pagina
        self.pagina_atual = 0
        self.total_paginas = max(1, (len(playlist) + itens_por_pagina - 1) // itens_por_pagina)
        self.atualizar_botoes()

    def atualizar_botoes(self):
        self.primeira.disabled = self.pagina_atual == 0
        self.anterior.disabled = self.pagina_atual == 0
        self.proxima.disabled = self.pagina_atual >= self.total_paginas - 1
        self.ultima.disabled = self.pagina_atual >= self.total_paginas - 1

    def criar_embed(self):
        embed = discord.Embed(title=self.titulo, color=0x00FF00)

        if not self.playlist:
            embed.description = "A playlist está vazia."
        else:
            inicio = self.pagina_atual * self.itens_por_pagina
            fim = inicio + self.itens_por_pagina
            itens_pagina = self.playlist[inicio:fim]

            descricao = ""
            for item in itens_pagina:
                pos = item.get('posicao_shuffle', item['posicao'])
                tocado_label = ' ✅' if item.get('tocado') else ''
                descricao += f"**{pos}.** [{item['titulo']}]({item['embed_url']}){tocado_label}\n"
                descricao += f"└ Por: {item['adicionado_por']} | ⏱️ {item['duracao_formatada']}\n\n"
            embed.description = descricao
            
            # Monta o footer com informações de paginação e shuffle_id se disponível
            footer_text = f"Página {self.pagina_atual + 1}/{self.total_paginas} | Total: {len(self.playlist)} vídeos"
            if self.playlist and self.playlist[0].get('shuffle_id'):
                footer_text += f" | Shuffle ID: {self.playlist[0].get('shuffle_id')}"
            embed.set_footer(text=footer_text)

        return embed

    @discord.ui.button(label="⏮️", style=discord.ButtonStyle.secondary)
    async def primeira(self, interaction: discord.Interaction, button: Button):
        self.pagina_atual = 0
        self.atualizar_botoes()
        await interaction.response.edit_message(embed=self.criar_embed(), view=self)

    @discord.ui.button(label="◀️", style=discord.ButtonStyle.primary)
    async def anterior(self, interaction: discord.Interaction, button: Button):
        self.pagina_atual = max(0, self.pagina_atual - 1)
        self.atualizar_botoes()
        await interaction.response.edit_message(embed=self.criar_embed(), view=self)

    @discord.ui.button(label="▶️", style=discord.ButtonStyle.primary)
    async def proxima(self, interaction: discord.Interaction, button: Button):
        self.pagina_atual = min(self.total_paginas - 1, self.pagina_atual + 1)
        self.atualizar_botoes()
        await interaction.response.edit_message(embed=self.criar_embed(), view=self)

    @discord.ui.button(label="⏭️", style=discord.ButtonStyle.secondary)
    async def ultima(self, interaction: discord.Interaction, button: Button):
        self.pagina_atual = self.total_paginas - 1
        self.atualizar_botoes()
        await interaction.response.edit_message(embed=self.criar_embed(), view=self)
