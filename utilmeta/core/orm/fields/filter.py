import inspect
from utype import Field
from utype.parser.field import ParserField
from utype.types import *

if TYPE_CHECKING:
    from ..backends.base import ModelAdaptor, ModelFieldAdaptor


class Filter(Field):
    def __init__(self,
                 field=None,
                 # allow at most 1 operator in 1 Filter to provide clarity
                 *,
                 query=None,  # expression to convert a input string to a Q object,
                 order: Union[str, list, Callable] = None,   # use order only if this filter is provided
                 # like order_by [1, 4, 2]
                 # lambda val: Case(*[When(**{field: v, 'then': pos}) for pos, v in enumerate(val)])
                 fail_silently: bool = False,
                 required: bool = False,
                 **kwargs
                 ):
        self.field = field
        self.query = query
        self.order = order
        self.fail_silently = fail_silently
        super().__init__(**kwargs, required=required)


class ParserFilter(ParserField):
    field: 'Filter'
    field_cls = Filter

    def __init__(
            self,
            model: 'ModelAdaptor' = None,
            **kwargs
    ):
        super().__init__(**kwargs)
        from ..backends.base import ModelAdaptor, ModelFieldAdaptor
        self.model: Optional[ModelAdaptor] = None
        self.model_field: Optional[ModelFieldAdaptor] = None
        self.query: Optional[Callable] = None
        self.filter = self.field if isinstance(self.field, Filter) else Filter()

        if isinstance(model, ModelAdaptor):
            self.model = model

            if isinstance(self.field, Filter):
                if self.field_name:
                    self.model_field = model.get_field(self.field_name, allow_addon=True, silently=True)
                    if self.model_field:
                        self.validate_field()
                    else:
                        if not self.filter.query:
                            raise ValueError(f'Filter({repr(self.field_name)}) '
                                             f'not resolved to field in model: {model.model}')
                if self.filter.query:
                    self.query = self.filter.query

                    if not inspect.isfunction(self.query):
                        self.model.check_query(self.query)

    @property
    def order(self):
        return self.filter.order

    @property
    def fail_silently(self):
        return self.filter.fail_silently

    @property
    def query_name(self):
        if isinstance(self.field, Filter):
            if self.field.query:
                return None
            if self.model_field:
                # including addon
                return self.model_field.query_name or self.name
        return self.name

    @property
    def filterable(self):
        return isinstance(self.field, Filter) or self.model_field

    def validate_field(self):
        if self.model_field.is_exp:
            self.model.check_expressions(self.model_field.field)
        self.model_field.check_query()

    @property
    def field_name(self):
        if isinstance(self.field, Filter):
            if self.field.field:
                return self.field.field
            if self.field.query:
                return None
        return self.attname