from utilmeta import utils
from utype.types import *
from utilmeta.utils.adaptor import BaseAdaptor
import json
from http.cookies import SimpleCookie


class ResponseAdaptor(BaseAdaptor):
    json_decoder_cls = json.JSONDecoder

    def __init__(self, response):
        self.response = response
        # self.request = request
        self._context = {}
        self._body = None

    @classmethod
    def reconstruct(cls, adaptor):
        if isinstance(adaptor, cls):
            return adaptor.response
        raise NotImplementedError

    @property
    def status(self):
        raise NotImplementedError

    @property
    def reason(self):
        raise NotImplementedError

    @property
    def headers(self):
        raise NotImplementedError

    @property
    def cookies(self):
        return SimpleCookie(self.headers.get('set-cookie'))

    @property
    def body(self) -> bytes:
        raise NotImplementedError

    @utils.cached_property
    def charset(self) -> Optional[str]:
        ct = self.headers.get(utils.Header.TYPE)
        if not ct:
            return None
        ct = str(ct)
        for value in ct.split(';'):
            if value.strip().startswith('charset='):
                return value.split('=')[1].strip()
        return None

    @utils.cached_property
    def content_type(self) -> Optional[str]:
        ct = self.headers.get(utils.Header.TYPE)
        if not ct:
            return
        ct = str(ct)
        if ';' in ct:
            return ct.split(';')[0].strip()
        return ct

    @property
    def content_length(self) -> Optional[int]:
        return self.headers.get(utils.Header.LENGTH)

    @property
    def json_type(self):
        content_type = self.content_type
        if not content_type:
            return False
        return content_type == utils.RequestType.JSON

    @property
    def xml_type(self):
        content_type = self.content_type
        if not content_type:
            return False
        return content_type in (utils.RequestType.XML, utils.RequestType.APP_XML)

    @property
    def text_type(self):
        content_type = self.content_type
        if not content_type:
            return False
        return content_type.startswith('text')

    @property
    def file_type(self):
        content_type = self.content_type
        if not content_type:
            return False
        maj, sec = content_type.split('/')
        if maj in ('video', 'audio', 'image'):
            return True
        if sec == 'octet-stream':
            return True
        return False

    def get_content(self):
        """
        Parsed content:
        text/*           : str
        application/json : dict/list
        image/*          : Image
        """
        if self.json_type:
            return self.get_json()
        elif self.xml_type:
            return self.get_xml()
        elif self.file_type:
            return self.get_file()
        elif self.text_type:
            return self.get_text()
        return None

    def get_file(self):
        from io import BytesIO
        return BytesIO(self.body)
        # from utilmeta.utils.media import File
        # return File(file=BytesIO(self.body))

    def get_text(self) -> str:
        return self.body.decode(encoding=self.charset or 'utf-8', errors='replace')

    def get_json(self) -> Union[dict, list]:
        text = self.get_text()
        import json
        return json.loads(text, cls=self.json_decoder_cls)

    def get_xml(self):
        from xml.etree.ElementTree import XMLParser
        parser = XMLParser()
        parser.feed(self.body)
        return parser.close()

    async def async_load(self):
        self.__dict__['body'] = await self.async_read()
        return self.get_content()

    async def async_read(self):
        # default to
        return self.body

    def close(self):
        pass

    @property
    def total_traffic(self):
        resp_length = self.content_length or 0
        for key, val in self.headers.items():
            resp_length += len(key) + len(val)
        return resp_length
