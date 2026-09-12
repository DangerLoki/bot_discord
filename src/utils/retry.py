"""Utilitários de retry com backoff exponencial."""
import asyncio
from typing import Callable, TypeVar, Any

from src.logger import get_logger

logger = get_logger(__name__)

T = TypeVar('T')


async def retry_async(
    func: Callable,
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    *args,
    **kwargs
) -> Any:
    """Executa função assíncrona com retry exponencial.

    Args:
        func: Função assíncrona a executar
        max_retries: Número máximo de tentativas
        initial_delay: Delay inicial em segundos
        max_delay: Delay máximo em segundos
        backoff_factor: Multiplicador do delay a cada retry
        *args, **kwargs: Argumentos da função

    Returns:
        Resultado da função

    Raises:
        Exception: Levanta a última exceção se todas as tentativas falharem
    """
    delay = initial_delay
    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_exception = e
            if attempt < max_retries:
                logger.warning(
                    f'[RETRY] {func.__name__} falhou (tentativa {attempt + 1}/{max_retries + 1}). '
                    f'Aguardando {delay:.1f}s antes de retry: {type(e).__name__}: {e}'
                )
                await asyncio.sleep(delay)
                delay = min(delay * backoff_factor, max_delay)
            else:
                logger.error(
                    f'[RETRY] {func.__name__} falhou após {max_retries + 1} tentativas. '
                    f'Última exceção: {type(e).__name__}: {e}'
                )

    raise last_exception
