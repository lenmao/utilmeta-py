from utilmeta.core.request import Request
from utilmeta.core.request import var
from utilmeta.core.orm import ModelAdaptor
from utilmeta.utils import exceptions
from .base import BaseAuthentication
from typing import Any, Union


class JsonWebToken(BaseAuthentication):
    name = 'jwt'
    jwt_var = var.RequestContextVar('_jwt_token')

    def getter(self, request: Request, field = None):
        token_type, token = request.authorization
        if not token:
            return {}
        try:
            from jwt import JWT  # noqa
            from jwt.exceptions import JWTDecodeError  # noqa
            from jwt.jwk import OctetJWK  # noqa
            jwt = JWT()
            key = None
            if self.secret_key:
                key = OctetJWK(key=self.secret_key.encode())
        except ImportError:
            # jwt 1.7
            import jwt  # noqa
            from jwt.exceptions import DecodeError as JWTDecodeError  # noqa
            key = self.secret_key
        try:
            jwt_params = jwt.decode(token, key)  # noqa
        except JWTDecodeError:
            raise exceptions.BadRequest(f'invalid jwt token')
        return jwt_params

    def __init__(self,
                 encode_algorithm: str = 'HS256',
                 key: Union[str, Any] = None,
                 # jwk: Union[str, dict] = None,
                 # jwk json string / dict
                 # jwk file path
                 # jwk url
                 audience: str = None,
                 required: bool = False,
                 user_token_field: str = None
                 ):
        super().__init__(required=required)
        self.encode_algorithm = encode_algorithm
        self.secret_key = key
        # self.jwk = jwk
        self.audience = audience
        self.user_token_field = user_token_field

    def apply_user_model(self, user_model: ModelAdaptor):
        if self.user_token_field and not isinstance(self.user_token_field, str):
            self.user_token_field = user_model.field_adaptor_cls(self.user_token_field).name

    def login(self, request: Request, key: str = 'uid', expiry_age: int = None):
        user = var.user.get(request)
        if not user:
            return
        import time
        from utilmeta import service
        iat = time.time()
        inv = expiry_age
        token_dict = {
            'iat': iat,
            'iss': service.origin,
            key: user.pk
        }
        if inv:
            token_dict['exp'] = iat + inv
        try:
            from jwt import JWT  # noqa
            from jwt.jwk import OctetJWK  # noqa
            jwt = JWT()
            key = None
            if self.secret_key:
                key = OctetJWK(key=self.secret_key.encode())
            jwt_token = jwt.encode(token_dict, key=key, alg=self.encode_algorithm)
        except ImportError:
            # jwt 1.7
            import jwt  # noqa
            jwt_token = jwt.encode(  # noqa
                token_dict, self.secret_key,
                algorithm=self.encode_algorithm
            ).decode('ascii')
        self.jwt_var.set(request, jwt_token)
        return {self.user_token_field: jwt_token} if isinstance(self.user_token_field, str) else None
        # if conf.jwt_token_field:
        #     setattr(user, conf.jwt_token_field, jwt_token)
        #     user.save(update_fields=[conf.jwt_token_field])
        # request.jwt_token = jwt_token
        # return jwt_token

    def openapi_scheme(self) -> dict:
        return dict(
            type='http',
            scheme='bearer',
            description=self.description or '',
            bearerFormat='JWT',
        )
