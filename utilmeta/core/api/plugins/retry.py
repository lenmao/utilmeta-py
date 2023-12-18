from utilmeta.utils.plugin import Plugin
from utilmeta.core.request import Request
from utilmeta.core.response import Response
from utype.types import *
from utilmeta.utils.error import Error
from utilmeta.utils import exceptions
from utilmeta.utils import multi, class_func, time_now, get_interval, awaitable
from utype.parser.func import FunctionParser
import random
from utype.types import Float
from utype import exc

float_or_dt = Float | datetime


class MaxRetriesExceed(exceptions.ServerError):
    pass


class MaxRetriesTimeoutExceed(exceptions.ServerError):
    pass


class RetryPlugin(Plugin):
    function_parser_cls = FunctionParser
    max_retries_error_cls = MaxRetriesExceed
    max_retries_timeout_error_cls = MaxRetriesTimeoutExceed
    DEFAULT_RETRY_ON_STATUS = []
    DEFAULT_RETRY_ON_ERRORS = ()
    DEFAULT_RETRY_AFTER_HEADERS = ()

    def __init__(self,
                 max_retries: int = 1,
                 max_retries_timeout: Union[float, int, timedelta] = None,
                 retry_interval: Union[float, int, timedelta, List[float], List[int],
                                       List[timedelta], Callable] = None,
                 # a value: 1 / 15.5 / timedelta(seconds=3.5)
                 # a callable: will take 2 optional params (current_retries, max_retries)
                 # a list of values:  [1, 3, 10, 15, 30], will be mapped to each retries
                 retry_timeout: Union[float, int, timedelta, List[float], List[int],
                                      List[timedelta], Callable] = None,
                 retry_delta_ratio: float = None,
                 retry_on_errors: List[Type[Exception]] = None,
                 retry_on_statuses: List[int] = None,
                 retry_on_idempotent_only: bool = True,
                 retry_after_headers: Union[str, List[str]] = None,
                 ):
        super().__init__(locals())

        self.max_retries = max_retries
        self.max_retries_timeout = max_retries_timeout
        if callable(retry_interval) or class_func(retry_interval):
            retry_interval = self.function_parser_cls.apply_for(retry_interval).wrap()
        self.retry_interval = retry_interval
        if callable(retry_timeout) or class_func(retry_timeout):
            retry_timeout = self.function_parser_cls.apply_for(retry_timeout).wrap()
        self.retry_timeout = retry_timeout
        self.retry_delta_ratio = retry_delta_ratio
        if retry_on_errors and not multi(retry_on_errors):
            retry_on_errors = [retry_on_errors]
        self.retry_on_errors = retry_on_errors or self.DEFAULT_RETRY_ON_ERRORS  # can be inherited
        if retry_on_statuses and not multi(retry_on_statuses):
            retry_on_statuses = [retry_on_statuses]
        self.retry_on_statuses = retry_on_statuses or self.DEFAULT_RETRY_ON_STATUS
        self.retry_on_idempotent_only = retry_on_idempotent_only
        if retry_after_headers and not multi(retry_after_headers):
            retry_after_headers = [retry_after_headers]
        self.retry_after_headers = retry_after_headers or self.DEFAULT_RETRY_AFTER_HEADERS
        # self.max_retry_after = max_retry_after

    def whether_retry(self, response: Response = None, error: Error = None):
        """
        Can inherit and custom, like base on response's header values
        """
        if self.retry_on_idempotent_only:
            idempotent = response.request.adaptor.get_context('idempotent')
            if not idempotent:
                return False
        if response:
            if not self.retry_on_statuses:
                return False
            return response.status in self.retry_on_statuses
        if error:
            if not self.retry_on_errors:
                return False
            return isinstance(error.exception, self.retry_on_errors)
        return False

    def process_request(self, request: Request):
        current_retry = request.adaptor.get_context('retry_index') or 0
        if current_retry >= self.max_retries:
            raise MaxRetriesExceed(f'{self.__class__}: max_retries: {self.max_retries} exceeded')
        self.handle_max_retries_timeout(request, set_timeout=True)
        return request

    def handle_max_retries_timeout(self, request: Request, set_timeout: bool = False):
        if not self.max_retries_timeout:
            return
        start_time = request.time
        current_time = time_now()
        delta = (current_time - start_time).total_seconds() - self.max_retries_timeout
        if delta <= 0:
            # max retries time exceeded
            raise self.max_retries_timeout_error_cls(
                f'{self.__class__}: max_retries_timeout exceed for {delta} seconds')

        # reset request timeout
        if set_timeout:
            if self.retry_timeout:
                current_retry = request.adaptor.get_context('retry_index') or 0
                timeout = self.retry_timeout
                if callable(timeout):
                    timeout = timeout(current_retry, self.max_retries, self.max_retries_timeout)
                if multi(timeout):
                    timeout = timeout[min(len(timeout) - 1, current_retry)]
                timeout = get_interval(timeout, null=True)
                if timeout:
                    if self.retry_delta_ratio:
                        timeout = timeout + (random.random() * 2 - 1) * self.retry_delta_ratio * timeout

                request.set_timeout(timeout)

            if not request.timeout or request.timeout > delta:
                request.set_timeout(delta)

    def process_response(self, response: Response, api):
        request = response.request
        if not request:
            return response
        current_retry = request.get_context('retry_index') or 0
        if current_retry + 1 >= self.max_retries:
            # cannot retry
            return response
        if not self.whether_retry(response=response):
            return response
        if not self.handle_retry_after(request, response=response):
            return response
        self.handle_max_retries_timeout(request, set_timeout=False)
        return request  # return request to make SDK retry this request

    @awaitable(process_response)
    async def process_response(self, response: Response, api):
        request = response.request
        if not request:
            return response
        current_retry = request.get_context('retry_index') or 0
        if current_retry + 1 >= self.max_retries:
            # cannot retry
            return response
        if not self.whether_retry(response=response):
            return response
        if not await self.handle_retry_after(request, response=response):
            return response
        self.handle_max_retries_timeout(request, set_timeout=False)
        return request  # return request to make SDK retry this request

    def handle_error(self, request: Request, e: Error, api):
        current_retry = request.adaptor.get_context('retry_index') or 0
        if current_retry + 1 >= self.max_retries:
            # cannot retry
            return  # proceed to handle error instead of raise
        if not self.whether_retry(error=e):
            return
        if not self.handle_retry_after(request):
            return
        self.handle_max_retries_timeout(request, set_timeout=False)
        return request

    @awaitable(handle_error)
    async def handle_error(self, request: Request, e: Error, api):
        current_retry = request.adaptor.get_context('retry_index') or 0
        if current_retry + 1 >= self.max_retries:
            # cannot retry
            return  # proceed to handle error instead of raise
        if not self.whether_retry(error=e):
            return
        if not await self.handle_retry_after(request):
            return
        self.handle_max_retries_timeout(request, set_timeout=False)
        return request

    def get_retry_after(self, request: Request, response: Response = None) -> Optional[float]:
        """
        Treat 429 specially, cause the headers/data may indicate the next_request_time
        """
        # https://developer.mozilla.org/zh-CN/docs/Web/HTTP/Headers/Retry-After
        # https://stackoverflow.com/questions/16022624/examples-of-http-api-rate-limiting-http-response-headers

        current_time = time_now()
        start_time = request.time
        passed = (current_time - start_time).total_seconds()
        current_retry = request.adaptor.get_context('retry_index') or 0

        retry_after = None
        if response:
            # try to get retry after from response
            # this will override the init settings
            for name in self.retry_after_headers:
                retry_after = response.headers.get(name)
                if not retry_after:
                    continue
                try:
                    try_dt = float_or_dt(retry_after)
                    if isinstance(try_dt, datetime) and try_dt > current_time:
                        retry_after = (current_time - try_dt).total_seconds()
                    else:
                        retry_after = float(retry_after)
                    break
                except exc.ParseError:
                    continue
                # this header is maybe a seconds / unix timestamp / http date
                # we will need to guess

        if not retry_after:
            retry_after = self.retry_interval
            if not retry_after:
                return 0
            if callable(retry_after):
                # function parser can consume
                retry_after = retry_after(current_retry, self.max_retries, self.max_retries_timeout)
            if multi(retry_after):
                retry_after = retry_after[min(len(retry_after) - 1, current_retry)]
            retry_after = get_interval(retry_after, null=True)

        if isinstance(retry_after, (int, float)):
            if self.retry_delta_ratio:
                retry_after = retry_after + (random.random() * 2 - 1) * self.retry_delta_ratio * retry_after

            if self.max_retries_timeout:
                # cannot wait longer than the max timeout
                if self.max_retries_timeout:
                    if passed + retry_after > self.max_retries_timeout:
                        # we cannot wait
                        return None
        return retry_after

    def handle_retry_after(self, request: Request, response: Response = None):
        retry_after = self.get_retry_after(request, response)
        if retry_after is None:
            return False
        if retry_after:
            import time
            time.sleep(retry_after)
        return True

    @awaitable(handle_retry_after)
    async def handle_retry_after(self, request: Request, response: Response = None):
        retry_after = self.get_retry_after(request, response)
        if retry_after is None:
            return False
        if retry_after:
            import asyncio
            await asyncio.sleep(retry_after)
        return True
