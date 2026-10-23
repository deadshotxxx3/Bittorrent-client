def decode(data: bytes, index: int = 0) -> int | bytes | list | dict:
    if data[index] == ord("i"):
       return decode_int(data,index) 
    if chr(data[index]).isdigit():
        return decode_bytes(data,index)
    if data[index] == ord("l"):
        return decode_list(data,index)
    if data[index] == ord("d"):
        return decode_dict(data,index)


def decode_int(data: bytes, index: int) -> int:
    index += 1
    num = ""
    is_negative = data[index] == ord('-')
    if is_negative: index += 1
    while data[index] != ord("e")   :
        num += chr(data[index])
        index += 1
    return (-int(num),index + 1) if is_negative else (int(num),index + 1)


def decode_bytes(data: bytes, index: int) -> bytes:
    len_str = ""
    while data[index] != ord(":"):
        len_str += chr(data[index])
        index += 1
    index += 1
    new_pos = index + int(len_str)
    return (data[index:new_pos],new_pos)


def decode_list(data: bytes, index: int) -> list:
    dec = []
    index += 1
    while data[index] != ord("e"):
        result = decode(data,index)
        dec.append(result[0])
        index = result[1]
    return (dec, index + 1)


def decode_dict(data: bytes, index: int) -> dict:
    index += 1
    result = {}
    while data[index] != ord("e"):
        key = decode(data,index)
        index = key[1]
        value = decode(data,index)
        index = value[1]
        result[key[0]] = value[0]
    return (result, index + 1)


def encode(value) -> bytes:
    if isinstance(value, int):
        return encode_int(value)
    if isinstance(value, bytes):
        return encode_bytes(value)
    if isinstance(value, list):
        return encode_list(value)
    if isinstance(value, dict):
        return encode_dict(value)
    else:
        raise TypeError(f"Тип данных {type(value)} не поддерживает")


def encode_int(value: int) -> bytes:
    return f"i{value}e".encode()


def encode_bytes(value: bytes) -> bytes:
    return f"{len(value)}:".encode() + value


def encode_list(value: list) -> bytes:
    result = b"l"

    for x in value:
        result += encode(x)
    result += b"e"
    return result


def encode_dict(value: dict) -> bytes:
    value = dict(sorted(value.items()))
    result = b"d"

    for key, val in value.items():
        result += encode(key) + encode(val)
    result += b"e"
    return result