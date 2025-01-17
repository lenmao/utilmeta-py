from utilmeta.core import api, response, request, file
from utype.types import *
import utype
from utilmeta.utils import exceptions

test_var = request.var.RequestContextVar('test-id', cached=True)


class HookResponse(response.Response):
    result: str
    description = 'common response'


class CookieSchema(utype.Schema):
    sessionid: str = None
    csrftoken: str = None
    access_key: Optional[str] = utype.Field(length=32, default=None)


class HeaderSchema(utype.Schema):
    __options__ = utype.Options(case_insensitive=True)
    auth_token: str = utype.Field(alias="X-Auth-Token", length=12)
    meta: dict = utype.Field(alias="X-Meta-Data")
    cookie: CookieSchema


class TestResponse(response.Response):
    result_key = 'test'
    message_key = 'message'


class Test1Response(response.Response):
    result_key = 'test1'


class SubAPI(api.API):
    # test context var
    test_id: int = test_var

    @api.get
    def hello(self):
        return 'world'

    @api.get
    def test0(self) -> response.Response:
        return 'test0'

    @api.get
    def test1(self):
        return self.test_id

    @api.after(test1)
    def after_test1(self, r) -> Test1Response:
        return r

    @api.get
    def resp(self, test_id: int = test_id):
        return self.response({'resp': test_id})


class ParentAPI(api.API):
    sub: SubAPI
    response = TestResponse

    @api.get
    def hello(self):
        return 'world'

    @api.before(SubAPI)
    def assign_var(self, x_test_id: int = request.HeaderParam('X-Test-Id')):
        test_var.setter(self.request, x_test_id)


@api.route('the/api')
class TheAPI(api.API):
    @api.get
    def hello(self):
        return TestResponse('world', message='hello')


class TestAPI(api.API):
    # sub: SubAPI
    parent: ParentAPI = api.route('@parent')
    the: TheAPI
    common_state_header: int = request.HeaderParam('X-Common-State')

    class resp_response(response.Response):
        result: str
        result_key = "data"
        state_key = "code"
        message_key = "error"

    response = response.Response

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.q_value = None

    # ------------ TEST ROUTE
    @api.get("@special")  # invalid attr name as route
    def special_api(self) -> str:
        print('PATH:', self.request.path)
        return self.request.path

    @api.post("response")  # slot attr name as route
    def resp(
        self, status: int, error: str = "default"
    ) -> resp_response:
        # test response
        return self.resp_response(
            self.request.path,
            state=self.common_state_header,
            status=status,
            message=error,
        )

    @api.get("patch")  # http method as route
    def get_patch(self) -> str:
        return self.request.path

    @api.delete(get_patch)
    def delete_patch(self) -> str:
        return self.request.path

    # --------- TEST PATH
    @api.get("doc/{category}/{page}")
    def get_doc(self, category: str = request.PathParam('[a-zA-Z0-9-]{1,20}'),
                page: int = 1) -> Dict[str, int]:
        return {category: page}

    # ------- TEST QUERY
    @api.get
    def query(self, page: int, item: str = "default") -> Tuple[int, str]:
        return page, item

    class QuerySchema(utype.Schema):
        page: int = utype.Field(ge=1, le=10)
        item: Optional[str] = utype.Field(min_length=3, max_length=10)

    @api.get
    def query_schema(self, query: QuerySchema = request.Query) -> QuerySchema:
        return query

    @api.get
    def alias(
        self,
        cls_name: str = utype.Field(alias="class"),
        page: int = utype.Field(alias="@page", default=1),
    ) -> Dict[str, int]:
        return {cls_name: page}

    @api.get('/{path}')
    def fallback(self, path: str = request.FilePathParam):
        return path

    # ----- TEST BODY
    @api.post
    def upload(self, f: file.File = request.Body):
        return self.response(file=f)

    class DataSchema(utype.Schema):
        title: str = utype.Field(min_length=3, max_length=10)
        views: int = 0

    class MultiFormData(utype.Schema):
        name: str
        images: List[file.File]

    @api.post
    def multipart(self, data: MultiFormData = request.Body):
        return [
            data.name,
            len(data.images),
            sum([f.size for f in data.images])
        ]

    @api.put
    def batch(self, data: List[DataSchema] = request.Body) -> List[DataSchema]:
        return data

    @api.post("log/{y}/{m}/{level}")
    def log(
        self,
        year: Optional[int] = utype.Field(ge=2000, alias='y'),
        month: Optional[int] = utype.Field(ge=1, le=12, alias='m'),
        level: Optional[str] = utype.Field(enum=["INFO", "WARN", "ERROR"]),
        status: int = utype.Field(ge=100, le=600, default=200),
        data: DataSchema = request.Body(
            max_length=30,
            content_type=request.Body.FORM_URLENCODED,
        ),
    ) -> Tuple[int, int, str, int, DataSchema]:
        return year, month, level, status, data

    @api.patch
    def content(
        self,
        html: str = request.Body(max_length=100, content_type="text/html"),
    ) -> str:
        return html

    @api.put
    def update(
        self,
        image: file.File = request.BodyParam(max_length=10 * 1024),
        query: QuerySchema = request.Query,
        test_cookie: str = request.CookieParam(alias='test-cookie', default='default'),
        name: str = request.BodyParam(max_length=30),
        desc: str = request.BodyParam(max_length=200, default=""),
    ) -> dict:
        # print('UPDATE:', image, image.size, image.read())
        # print(test_cookie)
        return {
            'image': image.read(),
            'cookie': test_cookie,
            'name': name,
            'desc': desc,
            'page': query.page,
            'item': query.item
        }

    # ------- TEST headers

    @api.post
    def operation(
        self,
        dic: Dict[int, Tuple[str, Dict[str, bool], List[int]]] = request.Body,
        # tf: file.FileType('*/xml') = request.BodyParam,
        x_test_header: int = request.HeaderParam(default=0),
        headers: HeaderSchema = request.Headers,
    ) -> Tuple[
        str,
        dict,
        CookieSchema,
        Dict[int, Tuple[str, Dict[str, bool], List[int]]],
    ]:
        print(x_test_header)
        return headers.auth_token, headers.meta, headers.cookie, dic  # noqa

    @api.post
    def headers_kwargs(
        self,
        q: int = request.QueryParam(gt=0),
        data: DataSchema = request.Body,
        x_test_id: int = request.HeaderParam('X-Test-ID'),
    ) -> Tuple[int, int, DataSchema]:
        return x_test_id, q, data

    # class FileData(utype.Schema):
    #     files: List[file.File] = utype.Field(max_length=10)

    @api.handle('*', exceptions.BadRequest)
    def handle_bad_request(self, e):
        return HookResponse(error=e, status=422)

    @api.handle('*', Exception)
    def handle_errors(self, e):
        return HookResponse(error=e)

    @api.after('*')
    def add_response(self) -> HookResponse: pass

    # class FilesData(utype.Schema):
    #     name: str
    #     files: List[file.File] = utype.Field(max_length=10)

    @api.post
    def upload(self, data: file.File = request.Body):
        # for i, f in enumerate(data.files):
        #     f.save(f'/tmp/{data.name}-{i}')
        return data.read()


class UserAPI(api.API):
    sessionid: str = request.CookieParam(required=True)
    csrftoken: str = request.CookieParam(default=None)

    @api.post
    def operation(self):
        return [self.sessionid, self.csrftoken]


# class RootAPI(api.API):
#     response = response.Response
#     test: TestAPI
