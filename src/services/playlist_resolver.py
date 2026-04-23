"""Resolução de entrada ambígua por título para operações de playlist."""
import asyncio

from src.logger import get_logger
from src.utils import embed_aviso

logger = get_logger(__name__)


async def resolver_entrada_por_titulo(ctx, bot, playlist: list, entrada: str):
    """Resolve uma string de título para (index, video, msg).

    Retorna (None, None, None) se cancelado ou não encontrado.
    Retorna (idx, video, msg) em caso de sucesso; msg pode ser None se a
    correspondência foi exata (sem confirmação necessária).
    """
    entrada_lower = entrada.lower()
    candidatos = []
    for i, v in enumerate(playlist):
        titulo = v.get('titulo', '')
        if entrada_lower == titulo.lower():
            return i, v, None
        if entrada_lower in titulo.lower():
            candidatos.append((i, v))

    if not candidatos:
        return None, None, None

    if len(candidatos) == 1:
        idx, video = candidatos[0]
        embed_confirm = _embed_confirmacao(video)
        msg = await ctx.send(embed=embed_confirm)
        await msg.add_reaction('✅')
        await msg.add_reaction('❌')

        def check_reacao(reaction, user):
            return (
                user == ctx.author
                and reaction.message.id == msg.id
                and str(reaction.emoji) in ('✅', '❌')
            )

        try:
            reaction, _ = await bot.wait_for('reaction_add', check=check_reacao, timeout=30.0)
        except asyncio.TimeoutError:
            await msg.edit(embed=embed_aviso('⏰ Tempo esgotado. Promoção cancelada.'))
            return None, None, None

        if str(reaction.emoji) == '✅':
            return idx, video, msg
        await msg.edit(embed=embed_aviso('❌ Promoção cancelada.'))
        return None, None, None

    # Múltiplos candidatos
    import discord

    max_mostrar = min(len(candidatos), 9)
    emojis = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣']
    descricao = 'Encontrei mais de um resultado. Qual você quer promover?\n\n'
    for i in range(max_mostrar):
        _, video = candidatos[i]
        descricao += f"{emojis[i]} **{video.get('titulo', 'Desconhecido')}**\n"
    descricao += '\nReaja com o número da opção desejada.'
    embed = discord.Embed(title='🔍 Múltiplos Resultados', description=descricao, color=0x5865F2)
    msg = await ctx.send(embed=embed)
    for emoji in emojis[:max_mostrar]:
        await msg.add_reaction(emoji)

    def check_multi(reaction, user):
        return (
            user == ctx.author
            and reaction.message.id == msg.id
            and reaction.emoji in emojis[:max_mostrar]
        )

    try:
        reaction, _ = await bot.wait_for('reaction_add', check=check_multi, timeout=30.0)
    except asyncio.TimeoutError:
        await msg.edit(embed=embed_aviso('⏰ Tempo esgotado. Promoção cancelada.'))
        return None, None, None

    escolha = emojis.index(reaction.emoji)
    idx, video = candidatos[escolha]
    return idx, video, msg


def _embed_confirmacao(video: dict):
    import discord

    embed = discord.Embed(
        title='🔍 Confirmar Promoção',
        description=(
            f'Você quis dizer:\n\n**{video.get("titulo", "Desconhecido")}**\n\n'
            'Reaja com ✅ para confirmar ou ❌ para cancelar.'
        ),
        color=0x5865F2,
    )
    embed.set_thumbnail(url=video.get('thumbnail_url', ''))
    return embed
