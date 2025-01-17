from typing import Union, Callable, Type, TypeVar, Optional
import sys
import os
from utilmeta.utils import import_obj, awaitable, search_file, cached_property
from utilmeta.conf.base import Config
import inspect
from utilmeta.core.api import API

# if TYPE_CHECKING:
#     from utilmeta.core.api.specs.base import BaseAPISpec

T = TypeVar('T')


class UtilMeta:
    # DEFAULT_API_SPEC = 'utilmeta.core.api.specs.openapi.OpenAPI'

    def __init__(
        self,
        module_name: Optional[str], *,
        backend,
        name: str,
        title: str = None,
        description: str = None,
        production: bool = None,
        host: str = None,
        port: int = None,
        scheme: str = 'http',
        origin: str = None,
        version: Union[str, tuple] = None,
        # application=None,
        info: dict = None,
        # for document generation
        background: bool = False,
        asynchronous: bool = None,
        auto_reload: bool = None,
        api=None,
        route: str = '',
    ):
        """
            ! THERE MUST BE NO IMPORT BEFORE THE CONFIG IS ASSIGNED PROPERLY !
            if there is, the utils will use the incorrect initial settings Config and cause the
            runtime error (hard to find)
        """

        # if not name.replace('-', '_').isidentifier():
        #     raise ValueError(f'{self.__class__}: service name ({repr(name)}) should be a valid identifier')

        self.module = sys.modules.get(module_name or '__main__')

        # 1. find meta.ini
        # 2. os.path.dirname(self.module.__file__)
        # 3. sys.path[0] / os.getcwd()
        self.meta_path = search_file('meta.ini')
        self.project_dir = os.path.dirname(self.meta_path) if self.meta_path else os.getcwd()

        self.root_api = api
        self.root_url = str(route or '').strip('/')
        # self.root_url = str(root_url).strip('/')
        self.production = production
        self.version = version
        # self.config = config
        self.background = background
        self.asynchronous = asynchronous

        # print('MODULE NAME:', module_name)
        if not name:
            raise ValueError('UtilMeta service detect empty <name>')
        self.name = name

        self.title = title
        self.description = description
        self.module_name = module_name
        self.host = host or '127.0.0.1'
        self.port = port
        self.scheme = scheme
        self.auto_reload = auto_reload
        self.info = info
        self.configs = {}
        self.commands = {}
        self.events = {}
        self.document = None
        # generated API document will be here

        self._origin = origin
        self._application = None
        self._ready = False

        import utilmeta
        try:
            srv: 'UtilMeta' = utilmeta.service
        except AttributeError:
            utilmeta.service = self
        else:
            if srv.name != self.name:
                raise ValueError(f'Conflict service: {repr(self.name)}, {srv.name} in same process')
            utilmeta.service = self

        self.backend = None
        self.backend_name = None
        self.backend_version = None

        from utilmeta.core.server.backends.base import ServerAdaptor
        self.adaptor: Optional[ServerAdaptor] = None
        self.set_backend(backend)

        self.routes = {}

        self._pool = None

    def set_backend(self, backend):
        if not backend:
            return

        from utilmeta.core.server.backends.base import ServerAdaptor

        backend_version = None
        application = None
        # backend_name = None

        if isinstance(backend, str):
            backend_name = backend
            backend = import_obj(backend_name)
        elif isinstance(backend, type) and issubclass(backend, ServerAdaptor):
            self.adaptor = backend(self)
            backend = backend.backend
            backend_name = getattr(backend, '__name__', str(backend))
        elif inspect.ismodule(backend):
            backend_name = getattr(backend, '__name__', str(backend))
        else:
            # maybe an application
            module = getattr(backend, '__module__', None)
            if module and callable(backend):
                # application
                application = backend
                backend_name = str(module).split('.')[0]
                backend = import_obj(backend_name)
            else:
                raise TypeError(f'Invalid service backend: {repr(backend)}, '
                                f'must be a supported module or application')

        if backend:
            backend_version = getattr(backend, '__version__', None)
            if backend_version is None:
                from importlib.metadata import version
                backend_version = version(backend_name)

        self.backend = backend
        self.backend_name = backend_name
        self.backend_version = backend_version

        if application:
            self._application = application

        if not self.adaptor:
            self.adaptor = ServerAdaptor.dispatch(self)
            self.port = self.port or self.adaptor.DEFAULT_PORT

        if self._application and self.adaptor.application_cls:
            if not isinstance(self._application, self.adaptor.application_cls):
                raise ValueError(f'Invalid application for {repr(self.backend_name)}: {application}')

    def __repr__(self):
        return f'UtilMeta({repr(self.module_name)}, ' \
               f'name={repr(self.name)}, ' \
               f'backend={self.backend}, ' \
               f'version={self.version}, background={self.background})'

    def __str__(self):
        return self.__repr__()

    @property
    def version_str(self):
        if isinstance(self.version, str):
            return self.version
        if not isinstance(self.version, tuple):
            return '1.0'
        parts = []
        for i, v in enumerate(self.version):
            parts.append(str(v))
            if i < len(self.version) - 1:
                if isinstance(self.version[i + 1], int):
                    parts.append('.')
                else:
                    parts.append('-')
        return ''.join(parts)

    def register_command(self, command_cls, name: str = None):
        from utilmeta.bin.base import BaseCommand
        if not issubclass(command_cls, BaseCommand):
            raise TypeError(f'UtilMeta: Invalid command class: {command_cls} to register, '
                            f'must be subclass of BaseCommand')
        if name:
            if name in self.commands:
                if self.commands[name] != command_cls:
                    raise ValueError(f'UtilMeta: conflict command'
                                     f' [{repr(name)}]: {command_cls}, {self.commands[name]}')
                return
            self.commands[name] = command_cls
        else:
            self.commands.setdefault(None, []).append(command_cls)

    def use(self, config):
        if isinstance(config, Config):
            config.hook(self)
        if isinstance(config, type):
            self.configs[config] = config()
        elif isinstance(config, object):
            self.configs[config.__class__] = config

    def get_config(self, config_class: Type[T]) -> Optional[T]:
        obj = self.configs.get(config_class)
        if obj:
            return obj
        for cls, config in self.configs.items():
            if issubclass(cls, config_class):
                return config
        return None

    def get_client(self, live: bool = False, backend=None):
        from utilmeta.core.cli.base import Client
        return Client(service=self, internal=not live, backend=backend)

    def setup(self):
        if self._ready:
            return
        for cls, config in self.configs.items():
            if isinstance(config, Config):
                config.setup(self)
        self._ready = True

    def startup(self):
        for cls, config in self.configs.items():
            if isinstance(config, Config):
                config.on_startup(self)
        for func in self.events.get('startup', []):
            func()

    @awaitable(startup)
    async def startup(self):
        for cls, config in self.configs.items():
            if isinstance(config, Config):
                r = config.on_startup(self)
                if inspect.isawaitable(r):
                    await r
        for func in self.events.get('startup', []):
            r = func()
            if inspect.isawaitable(r):
                await r

    def shutdown(self):
        for cls, config in self.configs.items():
            if isinstance(config, Config):
                config.on_shutdown(self)
        for func in self.events.get('shutdown', []):
            func()

    @awaitable(shutdown)
    async def shutdown(self):
        for cls, config in self.configs.items():
            if isinstance(config, Config):
                r = config.on_shutdown(self)
                if inspect.isawaitable(r):
                    await r
        for func in self.events.get('shutdown', []):
            r = func()
            if inspect.isawaitable(r):
                await r

    def on_startup(self, f):
        if callable(f):
            self.events.setdefault('startup', []).append(f)

    def on_shutdown(self, f):
        if callable(f):
            self.events.setdefault('shutdown', []).append(f)

    def mount(self, api=None, route: str = ''):
        if not api:
            def deco(_api):
                return self.mount(_api, route=route)
            return deco
        elif isinstance(api, str):
            pass
        elif inspect.isclass(api) and issubclass(api, API):
            pass
        else:
            # try to mount a wsgi/asgi app
            if not route:
                raise ValueError('Mounting applications required not-empty route')
            if not self.adaptor:
                raise ValueError('UtilMeta: backend is required to mount applications')
            self.adaptor.mount(api, route=route)
            return

        if self.root_api:
            if self.root_api != api:
                raise ValueError(f'UtilMeta: root api conflicted: {api}, {self.root_api}, '
                                 f'you can only mount a service once')
            return
        self.root_api = api
        self.root_url = str(route).strip('/')

    # def mount_ws(self, ws: Union[str, Callable], route: str = ''):
    #     pass

    def resolve(self):
        if callable(self.root_api):
            return self.root_api
        if isinstance(self.root_api, str):
            if '.' not in self.root_api:
                # in current module
                root_api = getattr(self.module, self.root_api)
            else:
                root_api = import_obj(self.root_api)
            self.root_api = root_api
        if not callable(self.root_api):
            raise ValueError(f'utilMeta: api not mount')
        return self.root_api

    def print_info(self):
        from utilmeta import __version__
        from utilmeta.bin.constant import BLUE, GREEN, DOT
        print(BLUE % '|', f'UtilMeta v{__version__} starting service [%s]' % (BLUE % self.name))
        print(BLUE % '|', '    version:', self.version_str)
        print(BLUE % '|', '      stage:', (BLUE % f'{DOT} production') if self.production else (GREEN % f'{DOT} debug'))
        print(BLUE % '|', '    backend:', f'{self.backend_name} ({self.backend_version})',
              (BLUE % f'| asynchronous') if self.asynchronous else '')
        print(BLUE % '|', '   base url:', f'{self.base_url}')
        print('')

    def run(self, **kwargs):
        if not self.adaptor:
            raise NotImplementedError('UtilMeta: service backend not specified')
        self.print_info()
        self.setup()
        return self.adaptor.run(**kwargs)

    def application(self):
        if not self.adaptor:
            raise NotImplementedError('UtilMeta: service backend not specified')
        self.setup()
        app = self.adaptor.application()
        self._application = app
        return app

    @property
    def origin(self):
        if self._origin:
            return self._origin
        host = self.host or '127.0.0.1'
        port = self.port
        if port == 80 and self.scheme == 'http':
            port = None
        elif port == 443 and self.scheme == 'https':
            port = None
        if port:
            host += f':{port}'
        return f'{self.scheme or "http"}://{host}'

    @property
    def base_url(self):
        if self.root_url:
            return self.origin + '/' + self.root_url
        return self.origin

    @property
    def pool(self):
        from utilmeta.conf.pool import ThreadPool
        pool = self.get_config(ThreadPool)
        if not pool:
            pool = ThreadPool()
        self._pool = pool
        return pool

    @cached_property
    def ip(self):
        from utilmeta.utils import get_server_ip
        return get_server_ip()
