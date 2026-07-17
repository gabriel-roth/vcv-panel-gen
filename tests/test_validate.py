import os
import sys
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from validate import validate_svg, ValidationError


def test_clean_svg_passes():
    validate_svg('<svg><g><circle cx="1" cy="2" r="2" fill="#f00"/></g></svg>')


def test_rejects_text_element():
    with pytest.raises(ValidationError, match="text"):
        validate_svg('<svg><text>hi</text></svg>')


def test_rejects_transform():
    with pytest.raises(ValidationError, match="transform"):
        validate_svg('<svg><g transform="translate(1,2)"></g></svg>')
