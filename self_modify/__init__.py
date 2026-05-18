"""self_modify - Safe code self-modification with lazy imports."""

def read_module(*a, **kw):
    from .code_reader import read_module as _f
    return _f(*a, **kw)

def list_modules(*a, **kw):
    from .code_reader import list_modules as _f
    return _f(*a, **kw)

def get_module_summary(*a, **kw):
    from .code_reader import get_module_summary as _f
    return _f(*a, **kw)

def apply_modification(*a, **kw):
    from .code_modifier import apply_modification as _f
    return _f(*a, **kw)

def validate_syntax(*a, **kw):
    from .code_modifier import validate_syntax as _f
    return _f(*a, **kw)

def rollback(*a, **kw):
    from .code_modifier import rollback as _f
    return _f(*a, **kw)
