try:
    import pydantic
    BaseModel = pydantic.BaseModel
except Exception:                 # Pydantic not installed (or import error)
    pydantic = None
    BaseModel = None


def is_model(value) -> bool:
    return BaseModel is not None and isinstance(value, BaseModel)


def is_model_type(annotation) -> bool:
    return (BaseModel is not None
            and isinstance(annotation, type)
            and issubclass(annotation, BaseModel))
