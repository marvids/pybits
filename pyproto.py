#!/usr/bin/python

import json
import collections
from bitstring import ConstBitStream


# Python 3.x compatibility
try:
  basestring
except NameError:
  basestring = str


class Field(collections.OrderedDict):
    def __init__(self, name=None, *args, **kwargs):
        super(Field, self).__init__(*args, **kwargs)
        self.name = name

    def __str__(self):
        s = ''
        if self.name:
            s += self.name + ' = '
        return s + json.dumps(self, indent=4)


class FieldParser:
    def __init__(self, *args, **kwargs):
        args, kwargs = self.__handleOptionalName(args, kwargs)
        self.init(*args, **kwargs)

    def __handleOptionalName(self, args, kwargs):
        if len(args) > 0 and isinstance(args[0], basestring):
            self.name = args[0]
            args = args[1:]
        elif 'name' in kwargs:
            self.name = kwargs['name']
            del kwargs['name']
        else:
            self.name = None
        return args, kwargs

    def __call__(self, name):
        self.name = name

    def init(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def unserialize(self, data):
        return self.parse(ConstBitStream(data))


class Sequence(FieldParser):
    def parse(self, stream):
        message = Field(self.name)
        for token in self.args:
            value = token.parse(stream)
            if token.name:
                message[token.name] = value
            elif value:
                message.update(value)
        return message


    def __add__(self, other):
        tokens = self.args + other.args
        return Sequence(*tokens)


class Choice(FieldParser):
    def init(self, fmt, alternatives):
        self.token = Bits(fmt)
        self.alternatives = alternatives

    def parse(self, stream):
        select = self.token.parse(stream)
        token = self.alternatives[select]
        value = token.parse(stream)
        if token.name:
            return Field(self.name, {token.name: value})
        return value


class Repeat(FieldParser):
    def init(self, sequence):
        self.sequence = sequence

    def parse(self, stream):
        l = []
        while stream.pos < stream.len:
            l.append(self.sequence.parse(stream))
        return l


class Bits(FieldParser):
    converter = None
    def init(self, fmt, converter=None, *args, **kwargs):
        if isinstance(fmt, int):
            self.fmt = str(fmt)
        else:
            self.fmt = fmt

        self.converter = converter
        self.converter_args = args
        self.converter_kwargs = kwargs

    def parse(self, stream):
        val = stream.read(self.fmt)
        if self.converter:
            return self.converter(val, *self.converter_args, **self.converter_kwargs)
        else:
            return val


class Enum(Bits):
    def init(self, fmt, enum, offset=0):
        def convertToEnum(value, enum, offset):
            def isUndefined(index, enum):
                if isinstance(enum, dict) and index not in enum:
                    return True
                if index >= len(enum) or index < 0:
                    return True
                return False

            index = value - offset
            if isUndefined(index, enum):
                result = '_UNDEFINED_({})'.format(value)
            else:
                result = enum[index]
            return result
        Bits.init(self, fmt, convertToEnum, enum, offset)


class Pad(Bits):
    def init(self, size):
        Bits.init(self, size)

    def parse(self, stream):
        Bits.parse(self, stream)


class Uint(Bits):
    pass


class Int(Bits):
    def init(self, size, *args, **kwargs):
        fmt = 'int:{}'.format(size)
        Bits.init(self, fmt, *args, **kwargs)


class Bool(Enum):
    def init(self, size=1, *args, **kwargs):
       Enum.init(self, size, ('FALSE', 'TRUE'), *args, **kwargs)


class Unit:
    factor = 1
    constant = 0
    unit = ''

    def __str__(self):
        return '\"{} {}\"'.format(self.factor*self + self.constant, self.unit)
