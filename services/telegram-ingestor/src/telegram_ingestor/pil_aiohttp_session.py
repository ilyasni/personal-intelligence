"""Сессия aiogram: явный ClientTimeout (connect/sock_connect), иначе aiohttp держит sock_connect=60s."""

from __future__ import annotations

import asyncio
from typing import cast

from aiohttp import ClientError, ClientTimeout
from aiogram.client.bot import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramNetworkError
from aiogram.methods import TelegramMethod
from aiogram.methods.base import TelegramType


class PilAiohttpSession(AiohttpSession):
    """Для цепочки SOCKS/VLESS: total и sock_connect совпадают с настройкой PIL."""

    def _client_timeout(self, seconds: float | None) -> ClientTimeout:
        t = float(seconds if seconds is not None else self.timeout)
        return ClientTimeout(total=t, connect=t, sock_connect=t, sock_read=t)

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[TelegramType],
        timeout: int | None = None,
    ) -> TelegramType:
        session = await self.create_session()
        url = self.api.api_url(token=bot.token, method=method.__api_method__)
        form = self.build_form_data(bot=bot, method=method)
        base = float(self.timeout)
        # aiogram передаёт per-method timeout (часто 60); для медленного прокси не ниже session timeout
        if timeout is None:
            sec = base
        else:
            sec = max(base, float(timeout))
        ct = self._client_timeout(sec)
        try:
            async with session.post(url, data=form, timeout=ct) as resp:
                raw_result = await resp.text()
        except asyncio.TimeoutError as e:
            raise TelegramNetworkError(method=method, message="Request timeout error") from e
        except ClientError as e:
            raise TelegramNetworkError(method=method, message=f"{type(e).__name__}: {e}") from e
        response = self.check_response(
            bot=bot,
            method=method,
            status_code=resp.status,
            content=raw_result,
        )
        return cast(TelegramType, response.result)
