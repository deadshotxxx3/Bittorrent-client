import pytest 
from core.bencode import decode

@pytest.mark.parametrize("data,expected",[
    (b"i52e",(52,4)),
    (b"i-42e",(-42,5)),
    (b"i0e",(0,3)),
])
def test_decode_int_cases(data,expected):
    assert decode(data) == expected

@pytest.mark.parametrize("data,expected",[
    (b"4:spam",(b"spam",6)),
    (b"0:",(b"",2)),
])
def test_decode_string_cases(data,expected):
    assert decode(data) == expected

@pytest.mark.parametrize("data,expected",[
    (b"li1ei2ee",([1, 2], 8)),
    (b"le",([],2)),
    (b"lli1eee",([[1]], 7)),
])
def test_decode_list_cases(data,expected):
    assert decode(data) == expected

@pytest.mark.parametrize("data,expected",[
    (b"d3:cow3:moee",({b"cow": b"moe"}, 12)),
    (b"d4:infod6:lengthi100eee",({b"info": {b"length": 100}}, 23)),
    (b"de",({},2)),

])
def test_decode_dict_cases(data,expected):
    assert decode(data) == expected