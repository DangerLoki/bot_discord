import discord


def embed_carregando(descricao: str) -> discord.Embed:
    """Embed roxo para estado de carregamento/processando."""
    return discord.Embed(description=descricao, color=0x5865F2)


def embed_erro(descricao: str) -> discord.Embed:
    """Embed vermelho para erros."""
    return discord.Embed(description=descricao, color=0xED4245)


def embed_aviso(descricao: str) -> discord.Embed:
    """Embed amarelo para avisos/informações."""
    return discord.Embed(description=descricao, color=0xFEE75C)


def embed_sucesso(descricao: str) -> discord.Embed:
    """Embed verde para confirmações de sucesso."""
    return discord.Embed(description=descricao, color=0x57F287)
