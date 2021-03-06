#-----------------------------------------------------------------------------
# Copyright (c) 2012 - 2018, Anaconda, Inc. and Intake contributors
# All rights reserved.
#
# The full license is in the LICENSE file, distributed with this software.
#-----------------------------------------------------------------------------

import collections
from contextlib import contextmanager
import yaml


def make_path_posix(path):
    """ Make path generic """
    if '://' in path:
        return path
    return path.replace('\\', '/').replace('//', '/')


def no_duplicates_constructor(loader, node, deep=False):
    """Check for duplicate keys while loading YAML

    https://gist.github.com/pypt/94d747fe5180851196eb
    """

    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        value = loader.construct_object(value_node, deep=deep)
        if key in mapping:
            from intake.catalog.exceptions import DuplicateKeyError

            raise DuplicateKeyError("while constructing a mapping",
                                    node.start_mark,
                                    "found duplicate key (%s)" % key,
                                    key_node.start_mark)
        mapping[key] = value

    return loader.construct_mapping(node, deep)


@contextmanager
def no_duplicate_yaml():
    yaml.SafeLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
        no_duplicates_constructor)
    try:
        yield
    finally:
        yaml.SafeLoader.add_constructor(
            yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
            yaml.constructor.SafeConstructor.construct_yaml_map
        )


def yaml_load(stream):
    """Parse YAML in a context where duplicate keys raise exception"""
    with no_duplicate_yaml():
        return yaml.safe_load(stream)


def classname(ob):
    """Get the object's class's name as package.module.Class"""
    import inspect
    if inspect.isclass(ob):
        return '.'.join([ob.__module__, ob.__name__])
    else:
        return '.'.join([ob.__class__.__module__, ob.__class__.__name__])


class DictSerialiseMixin(object):
    def __new__(cls, *args, **kwargs):
        """Capture creation args when instantiating"""
        from dask.base import tokenize
        o = object.__new__(cls)
        o._captured_init_args = args
        o._captured_init_kwargs = kwargs
        o.__dict__['_tok'] = tokenize(o.__getstate__())
        return o

    @property
    def classname(self):
        return classname(self)

    def __getstate__(self):
        args = [arg.__getstate__() if isinstance(arg, DictSerialiseMixin)
                else arg
                for arg in self._captured_init_args]
        kwargs = {k: arg.__getstate__() if isinstance(arg, DictSerialiseMixin)
                  else arg
                  for k, arg in self._captured_init_kwargs.items()}
        return dict(cls=self.classname,
                    args=args,
                    kwargs=kwargs)

    def __setstate__(self, state):
        # reconstitute instances here
        self._captured_init_kwargs = state['kwargs']
        self._captured_init_args = state['args']
        state.pop('cls', None)
        self.__init__(*state['args'], **state['kwargs'])

    def __hash__(self):
        return int(self._tok, 16)

    def __eq__(self, other):
        return hash(self) == hash(other)


def remake_instance(data):
    import importlib
    if isinstance(data, str):
        data = {'cls': data}
    else:
        data = data.copy()
    mod, klass = data.pop('cls').rsplit('.', 1)
    module = importlib.import_module(mod)
    cl = getattr(module, klass)
    return cl(*data.get('args', ()), **data.get('kwargs', {}))
