import tornado
from tornado.web import RequestHandler, Application
from utilmeta.core.response import Response
from utilmeta.core.request.backends.tornado import TornadoServerRequestAdaptor
from .base import ServerAdaptor
import asyncio
from utilmeta.core.api import API


class TornadoServerAdaptor(ServerAdaptor):
    backend = tornado
    request_adaptor_cls = TornadoServerRequestAdaptor
    application_cls = Application
    DEFAULT_PORT = 8000
    default_asynchronous = True

    def __init__(self, config):
        super().__init__(config)
        self.app = self.config._application

    def adapt(self, api: 'API', route: str, asynchronous: bool = None):
        if asynchronous is None:
            asynchronous = self.default_asynchronous
        func = self.get_request_handler(api, asynchronous=asynchronous)
        path = f'/{route.strip("/")}/(.*)' if route.strip('/') else '(.*)'
        return path, func

    def get_request_handler(self, utilmeta_api_class, asynchronous: bool = False):
        request_adaptor_cls = self.request_adaptor_cls
        service = self

        if asynchronous:
            class Handler(RequestHandler):
                @tornado.web.addslash
                async def get(self, *args, **kwargs):
                    return await self.handle(*args, **kwargs)

                @tornado.web.addslash
                async def put(self, *args, **kwargs):
                    return await self.handle(*args, **kwargs)

                @tornado.web.addslash
                async def post(self, *args, **kwargs):
                    return await self.handle(*args, **kwargs)

                @tornado.web.addslash
                async def patch(self, *args, **kwargs):
                    return await self.handle(*args, **kwargs)

                @tornado.web.addslash
                async def delete(self, *args, **kwargs):
                    return await self.handle(*args, **kwargs)

                @tornado.web.addslash
                async def head(self, *args, **kwargs):
                    return await self.handle(*args, **kwargs)

                @tornado.web.addslash
                async def options(self, *args, **kwargs):
                    return await self.handle(*args, **kwargs)

                async def handle(self, path: str):
                    try:
                        path = service.load_route(path)
                        request = request_adaptor_cls(self.request, path)
                        response: Response = await utilmeta_api_class(request)()
                        if not isinstance(response, Response):
                            response = Response(response)
                    except Exception as e:
                        response = getattr(utilmeta_api_class, 'response', Response)(error=e)
                    self.write(response.prepare_body())
                    self.set_status(response.status, reason=response.reason)
                    for key, value in response.prepare_headers(with_content_type=True):
                        self.add_header(key, value)
        else:
            class Handler(RequestHandler):
                @tornado.web.addslash
                def get(self, *args, **kwargs):
                    return self.handle(*args, **kwargs)

                @tornado.web.addslash
                def put(self, *args, **kwargs):
                    return self.handle(*args, **kwargs)

                @tornado.web.addslash
                def post(self, *args, **kwargs):
                    return self.handle(*args, **kwargs)

                @tornado.web.addslash
                def patch(self, *args, **kwargs):
                    return self.handle(*args, **kwargs)

                @tornado.web.addslash
                def delete(self, *args, **kwargs):
                    return self.handle(*args, **kwargs)

                @tornado.web.addslash
                def head(self, *args, **kwargs):
                    return self.handle(*args, **kwargs)

                @tornado.web.addslash
                def options(self, *args, **kwargs):
                    return self.handle(*args, **kwargs)

                def handle(self, path: str):
                    try:
                        path = service.load_route(path)
                        request = request_adaptor_cls(self.request, path)
                        response: Response = utilmeta_api_class(request)()
                    except Exception as e:
                        response = getattr(utilmeta_api_class, 'response', Response)(error=e)
                    self.write(response.prepare_body())
                    self.set_status(response.status, reason=response.reason)
                    for key, value in response.prepare_headers(with_content_type=True):
                        self.add_header(key, value)

        return Handler

    @property
    def request_handler(self):
        return self.get_request_handler(
            self.resolve(),
            asynchronous=self.asynchronous
        )

    def application(self):
        return self.setup()

    async def main(self):
        app = self.setup()
        app.listen(self.config.port or self.DEFAULT_PORT)
        await self.config.startup()
        try:
            await asyncio.Event().wait()
        finally:
            await self.config.shutdown()

    def setup(self):
        if self.app:
            return self.app
        self.app = self.application_cls([
            ('(.*)', self.request_handler)
        ])
        return self.app

    def run(self):
        asyncio.run(self.main())
