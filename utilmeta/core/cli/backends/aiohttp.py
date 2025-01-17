from .base import ClientRequestAdaptor
from aiohttp.client import ClientTimeout
import aiohttp


class AiohttpClientRequestAdaptor(ClientRequestAdaptor):
    # request: ClientRequest
    backend = aiohttp

    async def __call__(self, timeout: int = None, allow_redirects: bool = None, **kwargs):
        from utilmeta.core.response.backends.aiohttp import AiohttpClientResponseAdaptor
        async with aiohttp.ClientSession(timeout=ClientTimeout(total=timeout)) as session:
            resp = await session.request(
                method=self.request.method,
                url=self.request.url,
                data=self.request.body,
                headers=self.request.headers,
                allow_redirects=allow_redirects,
            )
            return AiohttpClientResponseAdaptor(resp)
