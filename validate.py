class ValidationError(Exception):
    pass


_FORBIDDEN_TAGS = ["<text", "<style", "<image", "<filter", "<mask", "<clipPath"]


def validate_svg(svg):
    for tag in _FORBIDDEN_TAGS:
        if tag in svg:
            raise ValidationError(
                f"Output contains forbidden element {tag!r} — NanoSVG cannot render it")
    if "transform=" in svg:
        raise ValidationError(
            "Output contains a 'transform=' attribute — bake coordinates instead")
