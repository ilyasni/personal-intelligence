"""Custom aiogram session with explicit connect and read timeouts."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramNetworkError
from aiohttp import ClientError, ClientTimeout

if TYPE_CHECKING:
    from aiogram.client.bot import Bot
    from aiogram.methods import TelegramMethod
    from aiogram.methods.base import TelegramType


class PilAiohttpSession(AiohttpSession):
    """Align aiogram HTTP timeouts with the configured proxy budget."""

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
        # Some Bot API methods pass a shorter timeout; keep it above the session baseline.
        sec = base if timeout is None else max(base, float(timeout))
        ct = self._client_timeout(sec)
        try:
            async with session.post(url, data=form, timeout=ct) as resp:
                raw_result = await resp.text()
        except TimeoutError as e:
            raise TelegramNetworkError(method=method, message="Request timeout error") from e
        except ClientError as e:
            raise TelegramNetworkError(method=method, message=f"{type(e).__name__}: {e}") from e
        response = self.check_response(
            bot=bot,
            method=method,
            status_code=resp.status,
            content=raw_result,
        )
        return cast("TelegramType", response.result)
