"""
This is a simple one-file project alternative when you setup UtilMeta project
"""
from utilmeta import UtilMeta
from utilmeta.core import api
import os
{import_backend}    # noqa

production = bool(os.getenv('UTILMETA_PRODUCTION'))
service = UtilMeta(
    __name__,
    name='{name}',
    description='{description}',
    backend={backend},  # noqa
    production=production,
    version=(0, 1, 0),
    host='{host}' if production else '127.0.0.1',
    port=80 if production else 8000,
)


class RootAPI(api.API):
    @api.get
    def hello(self):
        return 'world'


service.mount(RootAPI, route='/api')

app = service.application()     # used in wsgi/asgi server


if __name__ == '__main__':
    service.run()
    # try: http://127.0.0.1:8000/api/hello
