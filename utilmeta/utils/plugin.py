import inspect
import warnings
from utilmeta.utils.base import Util
from utilmeta.utils import awaitable
from typing import Type, Dict, List, Callable, Iterator, Union
from functools import partial
from utype.parser.func import FunctionParser
# from .context import Property


class Plugin(Util):
    def __init__(self, _kw=None, *args, **kwargs):
        super().__init__(_kw or kwargs)
        if inspect.isclass(self):
            try:
                self.__ref__ = f'{self.__module__}.{self.__qualname__}'
            except AttributeError:
                self.__ref__ = f'{self.__module__}.{self.__name__}'
        else:
            self.__name__ = f'{self.__class__.__name__}(...)'
            self.__ref__ = None
        self.__args__ = args

    @classmethod
    def apply_for(cls, target: 'PluginTarget') -> 'Plugin':
        return cls()

    def __call__(self, func, *args, **kwargs):
        if inspect.isfunction(func):
            if getattr(func, 'plugins', None):
                if self not in func.plugins:
                    # the later the plugin was decorated
                    # the earlier it will be applied
                    # like the way in the decorator
                    func.plugins.insert(0, self)
            else:
                func.plugins = [self]
        elif inspect.isclass(func) and issubclass(func, PluginTarget) or isinstance(func, PluginTarget):
            func._add_plugins(self)
        return func

    @classmethod
    def initialize(cls, params: dict = None,
                   default_value=None, ignore_required: bool = False):
        args = []
        kwargs = {}
        extras = {}
        params = params or {}

        def get_value(_name: str, _class: Type = cls):
            attr_value = getattr(_class, _name)
            if inspect.isclass(attr_value):
                if issubclass(attr_value, Plugin):
                    return attr_value.initialize(
                        params=params.get(key),
                        default_value=default_value,
                        ignore_required=ignore_required
                    )
                elif issubclass(attr_value, dict):  # like Schema
                    attr_dict = {}
                    for n in list(attr_value.__dict__):
                        if n.startswith('_'):
                            continue
                        if hasattr(dict, n):
                            continue
                        attr_dict[n] = get_value(n, _class=attr_value)
                    inst = attr_value(**attr_dict)    # use dict to initialize
                    for k, v in attr_dict.items():
                        setattr(inst, k, v)     # set to the new attribute
                    return inst
            elif inspect.isdatadescriptor(attr_value):  # has __set__ or __delete__
                # delete the attribute before initialize
                delattr(_class, _name)
            return attr_value

        for key in cls._pos_keys:
            if key not in cls._attr_names:
                if key in params:
                    args.append(params[key])
                    continue
                if key not in cls._requires:
                    # has default
                    continue
                if ignore_required:
                    args.append(default_value)
                    continue
                raise TypeError(f'{cls} required arg: {repr(key)} not defined')
            args.append(get_value(key))

        for key in cls._kw_keys:
            if key not in cls._attr_names:
                if key in params:
                    kwargs[key] = params[key]
                    continue
                if key not in cls._requires:
                    # has default
                    continue
                if ignore_required:
                    kwargs[key] = default_value
                    continue
                raise TypeError(f'{cls} required arg: {repr(key)} not defined')
            if key in kwargs:
                continue
            kwargs[key] = get_value(key)

        if cls._attr_names:
            for name in cls._attr_names:
                if not hasattr(cls, name):
                    continue
                if name in cls._kw_keys or name in cls._pos_keys:
                    continue
                # handle the extended attributes
                if name in extras:
                    continue
                extras[name] = get_value(name)
            if cls._key_var:
                kwargs.update(extras)

        if cls._pos_var:
            ext_args = params.get('@args')
            if ext_args:
                args.extend(ext_args)

        instance = cls(*args, **kwargs)
        if extras:
            for key, val in extras.items():
                if not hasattr(instance, key):
                    setattr(instance, key, val)

        return instance


class PluginEvent:
    function_parser_cls = FunctionParser

    def __init__(self, name: str, streamline_result: bool = False,
                 synchronous_only: bool = False,
                 asynchronous_only: bool = False):
        self.name = name
        self.streamline_result = streamline_result
        self.synchronous_only = synchronous_only
        self.asynchronous_only = asynchronous_only

        self._hooks: Dict[Type, List[tuple]] = {}
        self._callback_hooks = {}

    def __call__(self, inst: Union['PluginTarget', Type['PluginTarget']], *args, **kwargs):
        # inst can be PluginTarget instance or class
        result = None
        if self.streamline_result:
            pos = list(args)
            if pos:
                result = pos[0]
            for handler in self.iter(inst):
                if result is not None:
                    # set the new result
                    pos[0] = result
                result = handler(*pos, inst, **kwargs)
                if result is None:
                    result = pos[0]
        else:
            for handler in self.iter(inst):
                result = handler(*args, inst, **kwargs)
        return result

    @awaitable(__call__)
    async def __call__(self, inst: Union['PluginTarget', Type['PluginTarget']], *args, **kwargs):
        # inst can be PluginTarget instance or class
        result = None
        if self.streamline_result:
            pos = list(args)
            if pos:
                result = pos[0]
            for handler in self.iter(inst):
                if result is not None:
                    # set the new result
                    pos[0] = result
                result = handler(*pos, inst, **kwargs)
                if inspect.isawaitable(result):
                    result = await result
                if result is None:
                    result = pos[0]
        else:
            for handler in self.iter(inst):
                result = handler(*args, inst, **kwargs)
                if inspect.isawaitable(result):
                    await result
        return result

    def get_hooks(self, target):
        if not inspect.isclass(target):
            target_cls = target.__class__
        else:
            target_cls = target
        cls_hooks = []
        for base in target_cls.__bases__:
            # base is priority
            cls_hooks.extend(self.get_hooks(base))
        if target_cls in self._hooks:
            cls_hooks.extend(self._hooks.get(target_cls))
        return cls_hooks

    def iter(self, inst: 'PluginTarget') -> Iterator[Callable]:
        plugins = getattr(inst, '_plugins', {})
        if not plugins or not isinstance(plugins, dict):
            return
        hooks = self.get_hooks(inst)
        for plugin_cls, plugin in plugins.items():
            hooked = False
            for plugin_class, func, target_arg, priority in hooks:
                if plugin_cls == plugin_class:
                    hooked = True
                    # from hook, should particle first argument to plugin instance
                    partial_kw = {target_arg: inst} if target_arg else {}
                    yield partial(func, plugin, **partial_kw)
            if hooked:
                continue
            handler = getattr(plugin, self.name, None)
            # priority
            # 1. hook
            # 2, plugin.<event_name>
            if callable(handler):
                # already partial by instance method reference
                yield handler

    def register(self, target_class):
        if not inspect.isclass(target_class):
            raise TypeError(f'Invalid register class: {target_class}, must be a class')
        if target_class not in self._hooks:
            self._hooks.setdefault(target_class, [])

    def unregister(self, target_class):
        if target_class in self._hooks:
            self._hooks.pop(target_class)

    def make_callable(self, func, target_class):
        func = self.function_parser_cls.apply_for(func)
        if self.synchronous_only and func.is_asynchronous:
            raise TypeError(f'PluginEvent: {self.name} is synchronous only, got async function: {func}')
        if self.asynchronous_only and not func.is_asynchronous:
            raise TypeError(f'PluginEvent: {self.name} is asynchronous only, got sync function: {func}')
        target_arg = None
        for key, field in func.fields.items():
            annotate = field.type
            if inspect.isclass(annotate):
                if issubclass(annotate, target_class):
                    target_arg = annotate
            # else:
            #     _origin = getattr(annotate, '__origin__', None)
            #     if _origin == type:
            #         _arg = annotate.__args__[0]
            #         if inspect.isclass(_arg) and issubclass(_arg, target_class):
            #             target_arg = _arg
        return func, target_arg

    def add_callback_hook(self, func, target_class, priority=0, registered_only: bool = False):
        if not inspect.isclass(target_class):  # or not issubclass(target_class, PluginTarget):
            raise ValueError(f'{self.name}.hook target_class: {target_class} must be subclass of PluginTarget')
        if registered_only and target_class not in self._hooks:
            raise ValueError(f'{self.name}.hook target_class: {target_class} not registered')
        if target_class not in self._hooks:
            self.register(target_class)

        func, target_arg = self.make_callable(func, target_class=target_class)
        item = (
            func,
            target_arg,
            priority
        )
        if item not in self._callback_hooks[target_class]:
            self._callback_hooks[target_class].append(item)
            self._callback_hooks[target_class].sort(key=lambda tup: -tup[-1])

    def add_plugin_hook(self, func, target_class, plugin_class, priority=0, registered_only: bool = False):
        if not inspect.isclass(target_class):  # or not issubclass(target_class, PluginTarget):
            raise ValueError(f'{self.name}.hook target_class: {target_class} must be subclass of PluginTarget')
        if registered_only and target_class not in self._hooks:
            raise ValueError(f'{self.name}.hook target_class: {target_class} not registered')
        if target_class not in self._hooks:
            self.register(target_class)

        func, target_arg = self.make_callable(func, target_class=target_class)

        item = (
            plugin_class,
            func,
            target_arg,
            priority
        )
        if item not in self._hooks[target_class]:
            self._hooks[target_class].append(item)
            self._hooks[target_class].sort(key=lambda tup: -tup[-1])

    def hook_callback(self, target_class, priority=0):
        """
        Only pass the target instance/class
        """

        def wrapper(f):
            self.add_callback_hook(f, target_class=target_class, priority=priority)
            return f
        return wrapper

    def hook(self, target_class, plugin_class=None, *, priority=0, registered_only: bool = False):
        def wrapper(f):
            plugin = plugin_class
            if not plugin:
                for i, (k, v) in enumerate(inspect.signature(f).parameters.items()):
                    if not i:
                        if v.annotation:
                            if inspect.isclass(v.annotation):
                                plugin = v.annotation
                            else:
                                # like Type[Class]
                                _origin = getattr(plugin, '__origin__', None)
                                if _origin == type:
                                    _arg = plugin.__args__[0]
                                    if inspect.isclass(_arg):
                                        plugin = _arg
                    else:
                        break
            if not plugin:
                raise ValueError(f'{self.name}.hook does not specify plugin_class (either by param or annotation)')
            self.add_plugin_hook(f, target_class, plugin_class=plugin,
                                 priority=priority, registered_only=registered_only)
            return f
            # target_class._add_plugin_hook(self, f, plugin_class, priority=priority)
        return wrapper


class PluginLoader:
    def __init__(self, ref: str, *args, **kwargs):
        self.ref = ref
        self.args = args
        self.kwargs = kwargs

    # def __call__(self, *args, **kwargs):
    #     pass


class PluginTarget:
    __ref__: str
    _fixed_plugins: dict = {}
    _plugins: dict = {}

    def __init_subclass__(cls, **kwargs):
        cls.__ref__ = f'{cls.__module__}.{cls.__qualname__}'

        for key, val in cls.__annotations__.items():
            if inspect.isclass(val) and issubclass(val, Plugin):   # fixed plugins
                cls._fixed_plugins[key] = val

        plugins = dict(cls._plugins)
        for slot in list(cls.__dict__):
            if slot.startswith('_'):
                continue

            util = cls.__dict__[slot]

            if inspect.isclass(util) and issubclass(util, Plugin):
                util = util.initialize()
                cls.__dict__[slot] = util
                # set attribute

            # check fixed plugins
            if slot in cls._fixed_plugins:
                plugin_cls = cls._fixed_plugins.get(slot)
                if not isinstance(util, plugin_cls):
                    raise TypeError(f'{cls}.{slot} must be a {plugin_cls} instance, got {util}')
            # else:
            #     if isinstance(util, tuple(cls._fixed_plugins.values())):
            #         # if a util other than
            #         continue

            if isinstance(util, Plugin):
                path = f'{cls.__ref__}.{slot}'
                if util.__ref__:
                    if util.__ref__ != path:
                        warnings.warn(f'{cls} same util: {util} mount to different '
                                      f'path: {repr(path)}, {repr(util.__ref__)}')
                else:
                    util.__ref__ = path
            else:
                continue

            plugins[util.__class__] = util

        # set every class a different addr plugins
        cls._plugins = plugins

    def __init__(self, plugins=()):
        if isinstance(plugins, (list, tuple)) and plugins:
            self._init_plugins(list(plugins))

    @classmethod
    def _add_plugins(cls, *plugins):
        plugin_dict = {}
        for plugin in plugins:
            if inspect.isclass(plugin):
                if issubclass(plugin, Plugin):
                    plugin_dict[plugin] = plugin
                    continue
            elif isinstance(plugin, Plugin):
                plugin_dict[plugin.__class__] = plugin
                continue
            warnings.warn(f'{cls}: add invalid plugin: {plugin}, must be a {Plugin} subclass of instance')
        cls._plugins.update(plugin_dict)

    @classmethod
    def _get_plugin(cls, plugin_class):
        if plugin_class in cls._plugins:
            return cls._plugins[plugin_class]
        for _class, plugin in cls._plugins.items():
            if issubclass(_class, plugin_class):
                return plugin
        return None

    @classmethod
    def _remove_plugins(cls, *plugin_classes):
        for plugin_cls in plugin_classes:
            if plugin_cls in cls._plugins:
                cls._plugins.pop(plugin_cls)

    def _init_plugins(self, plugins: List[Union[Type[Plugin], Plugin]]):
        """
        Instance can dynamically pass a list of plugin in initialize
        """
        inst_plugins = dict()
        for cls, plugin in self.__class__._plugins.items():
            if inspect.isclass(plugin):
                plugin = plugin.apply_for(self)
            inst_plugins[cls] = plugin
        for plugin in plugins:
            if inspect.isclass(plugin):
                if not issubclass(plugin, Plugin):
                    continue
                plugin = plugin.apply_for(self)
            if not isinstance(plugin, Plugin):
                continue
            inst_plugins[plugin.__class__] = plugin
        self._plugins: Dict[Type[Plugin], Plugin] = inst_plugins
