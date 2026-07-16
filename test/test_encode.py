import pytest
from core.bencode import encode, decode


@pytest.mark.parametrize("raw", [
    b"i42e", b"4:spam", b"li1ei2ee", b"d3:cow3:moee",
])
def test_encode_decode_roundtrip(raw):
    assert encode(decode(raw)[0]) == raw

@pytest.mark.parametrize("data,expected",[
    (52, b"i52e"),
    (0, b"i0e"),
    (-42, b"i-42e")
])
def test_encode_int_cases(data,expected):
    assert encode(data) == expected

@pytest.mark.parametrize("data,expected",[
    (b"", b"0:"),
    (b"lol", b"3:lol"),
])
def test_encode_string_cases(data,expected):
    assert encode(data) == expected

@pytest.mark.parametrize("data,expected",[
    ([], b"le"),
    ([52,b's'], b"li52e1:se"),
    ([[[]]], b"llleee"),
])
def test_encode_list_cases(data,expected):
    assert encode(data) == expected

@pytest.mark.parametrize("data,expected",[
    ({b"cow":b"moo"},b"d3:cow3:mooe"),
    ({},b"de"),
    ({b"info": {b"length": 100}},b"d4:infod6:lengthi100eee")
])
def test_encode_dict_cases(data,expected):
    assert encode(data) == expected

def test_encode_unsupported_type_raises():
    with pytest.raises(TypeError):
        encode(3.14)