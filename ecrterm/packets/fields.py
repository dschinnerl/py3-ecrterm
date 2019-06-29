from enum import Enum
from typing import Any, Union, List, Optional, Tuple

from .tlv import TLVContainer

class ParseError(Exception):
    pass

class Endianness(Enum):
    BIG_ENDIAN = 3210
    LITTLE_ENDIAN = 123


class Field:
    REPR_FORMAT = "{!r}"

    def __init__(self, required=True, ignore_parse_error=False, *args, **kwargs):
        self.required = required
        self.ignore_parse_error = ignore_parse_error
        super().__init__(*args, **kwargs)

    def from_bytes(self, v: Union[bytes, List[int]]) -> Any:
        return v

    def to_bytes(self, v: Any, length: Optional[int] = None) -> bytes:
        return v

    def parse(self, data: Union[bytes, List[int]]) -> Tuple[Any, bytes]:
        raise NotImplementedError

    def serialize(self, data: Any) -> bytes:
        raise NotImplementedError

    def represent(self, data: Any) -> str:
        return self.REPR_FORMAT.format(data)

    def __set__(self, instance, value):
        instance._values[self] = value

    def __delete__(self, instance):
        instance._values[self] = None

    def __get__(self, instance, objtype=None):
        return instance._values.get(self, None)


class FixedLengthField(Field):
    LENGTH = None

    def __init__(self, length=None, *args, **kwargs):
        self.length = length or self.LENGTH
        if self.length is None:
            raise ValueError("Length must be set for fixed length fields")
        super().__init__(*args, **kwargs)

    def parse(self, data: Union[bytes, List[int]]) -> Tuple[Any, bytes]:
        data = bytes(data) if not isinstance(data, bytes) else data
        v, data = data[:self.length], data[self.length:]
        return self.from_bytes(v), data

    def serialize(self, data: Any) -> bytes:
        return self.to_bytes(data, self.length)


class LVARField(Field):
    LL = 1

    def parse(self, data: Union[bytes, List[int]]) -> Tuple[Any, bytes]:
        data = bytes(data) if not isinstance(data, bytes) else data
        l = 0
        for i in range(self.LL):
            if (data[i] & 0xF0) != 0xF0 or (data[i] & 0x0F) > 9:
                raise ParseError("L*VAR length header invalid")
            l = (l * 10) + (data[i] & 0x0F)
        data = data[self.LL:]

        v, data = data[:l], data[l:]

        return self.from_bytes(v), data

    def serialize(self, data: Any) -> bytes:
        data = self.to_bytes(data)

        l = len(data)
        if l >= (10 ** self.LL):
            raise ValueError("Data too long for L*VAR field")

        header = bytes(0xF0 | ((l // (10 ** i)) % 10) for i in reversed(range(self.LL)))
        return header + data


class LLVARField(LVARField):
    LL = 2


class LLLVARField(LVARField):
    LL = 3


class IntField(Field):
    LENGTH = None
    ENDIAN = Endianness.BIG_ENDIAN

    def to_bytes(self, v: int, length: Optional[int] = None) -> bytes:
        length = length if length is not None else (self.length if self.length is not None else self.LENGTH)
        if length is None:
            raise ValueError("Need to specify length for IntField serialization")

        result = [0] * length
        for i in range(length):
            n, v = v & 0xff, v >> 8
            if self.ENDIAN is Endianness.BIG_ENDIAN:
                result[length - 1 - i] = n
            else:
                result[i] = n

        return bytes(result)

    def from_bytes(self, v: Union[bytes, List[int]]) -> int:
        if self.ENDIAN is Endianness.LITTLE_ENDIAN:
            v = reversed(v)

        result = 0
        for n in v:
            result = (result << 8) | n

        return result


class StringField(Field):
    def parse(self, data: Union[bytes, List[int]]) -> Tuple[str, bytes]:
        return self.from_bytes(data), b''

    def serialize(self, data: str) -> bytes:
        return self.to_bytes(data)

    def from_bytes(self, v: Union[bytes, List[int]]) -> str:
        return bytes(v).decode()

    def to_bytes(self, v: str, length: int = None) -> bytes:
        if length:
            if len(v) != length:
                raise ValueError("String length doesn't match fixed string length")

        return bytes(v.encode())


class ByteField(IntField, FixedLengthField):
    LENGTH = 1
    REPR_FORMAT = "0x{:02X}"


class BCDField(FixedLengthField):
    def from_bytes(self, v: Union[bytes, List[int]]) -> str:
        return bytearray(v).hex()

    def to_bytes(self, v: str, length: Optional[int] = None) -> bytes:
        length = length if length is not None else (self.length if self.length is not None else self.LENGTH)
        if length is None:
            raise ValueError("Must specify length for BCDField")

        if length != len(v) / 2:
            raise ValueError("Value length doesn't match field length")

        if not v.isdigit():
            raise ValueError("BCD field contents can only be numeric")

        return bytes(bytearray.fromhex(v))


class PasswordField(BCDField):
    LENGTH = 3


class BCDIntField(BCDField):
    def from_bytes(self, v: Union[bytes, List[int]]) -> int:
        v = super().from_bytes(v)
        return int(v, 10)

    def to_bytes(self, v: int, length: Optional[int] = None) -> bytes:
        length = length if length is not None else (self.length if self.length is not None else self.LENGTH)
        v = str(v)
        return super().to_bytes(v.rjust(length*2, '0'), length)


class BEIntField(IntField, FixedLengthField):
    ENDIAN = Endianness.BIG_ENDIAN


class LLStringField(LLVARField, StringField):
    pass


class LLLStringField(LLLVARField, StringField):
    pass


class TLVField(Field):
    def from_bytes(self, v: Union[bytes, List[int]]) -> TLVContainer:
        return TLVContainer.from_bytes(bytes(v))

    def to_bytes(self, v: TLVContainer, length: Optional[int] = None) -> bytes:
        if length is not None:
            raise ValueError("Must not give length for TLV container")
        return v.to_bytes()

    def parse(self, data: Union[bytes, List[int]]) -> Tuple[TLVContainer, bytes]:
        return TLVContainer.parse(data)

    def serialize(self, data: TLVContainer) -> bytes:
        return data.serialize()