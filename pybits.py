#!/usr/bin/python

import copy
import json
import collections
from bitstring import ConstBitStream


# Python 3.x compatibility
try:
  basestring
except NameError:
  basestring = str


class Field:
    def __init__(self, name=None, parent=None):
        self.name = name
        self.parent = parent

    def __str__(self):
        s = ''
        if self.name:
            s += self.name + ' = '
        return s + json.dumps(self, indent=4)

    def findRef(self, reference):
        if reference.startswith('../'):
            return self.parent.findRef(reference[3:])
        elif reference.startswith('./'):
            reference = reference[2:]
        part = reference.partition('/')
        try:
            return self[part[0]].findRef(part[2])
        except AttributeError:
            return self[part[0]]


class DictField(Field, collections.OrderedDict):
    def __init__(self, name=None, parent=None, *args, **kwargs):
        Field.__init__(self, name, parent)
        collections.OrderedDict.__init__(self, *args, **kwargs)

    def __getattr__(self, name):
        if name in self:
            return self[name]
        raise AttributeError


class ListField(Field, list):
    def __init__(self, name=None, *args, **kwargs):
        Field.__init__(self, name)
        list.__init__(self, *args, **kwargs)


class FieldParser:
    def __init__(self, name, *args, **kwargs):
        self.name = name
        self.init(*args, **kwargs)

    def __call__(self, name):
        c = copy.copy(self)
        c.name = name
        return c

    def init(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def unserialize(self, data):
        return self.parse(ConstBitStream(data), None)


class Ref(str):
    pass

class Sequence(FieldParser):
    def parse(self, stream, parent):
        message = DictField(self.name, parent)
        for token in self.args:
            value = token.parse(stream, message)
            if token.name:
                message[token.name] = value
            elif value:
                message.update(value)
        return message


    def __add__(self, other):
        tokens = self.args + other.args
        return Sequence(None, *tokens)


class Choice(FieldParser):
    def init(self, fmt, alternatives):
        if isinstance(fmt, Ref):
            self.reference = fmt
        else:
            self.token = Bits(self.name, fmt)
        self.alternatives = alternatives

    def parse(self, stream, parent):
        try:
            select = self.token.parse(stream, parent)
        except AttributeError:
            select = parent.findRef(self.reference)

        token = self.alternatives[select]
        try:
            value = token.parse(stream, parent)
            if token.name:
                return DictField(self.name, parent, {token.name: value})
        except AttributeError:
            value = token
        return value


class Repeat(FieldParser):
    def init(self, sequence):
        self.sequence = sequence

    def parse(self, stream, parent):
        l = ListField()
        while stream.pos < stream.len:
            l.append(self.sequence.parse(stream, l))
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

    def parse(self, stream, parent):
        val = stream.read(self.fmt)
        if self.converter:
            return self.converter(val, *self.converter_args, **self.converter_kwargs)
        else:
            return val


class Pad(Bits):
    def __init__(self, size):
        Bits.__init__(self, None, size)

    def parse(self, stream, parent):
        Bits.parse(self, stream, parent)


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


class Uint(Bits):
    pass


class Int(Bits):
    def init(self, size, *args, **kwargs):
        fmt = 'int:{}'.format(size)
        Bits.init(self, fmt, *args, **kwargs)


class Bool(Enum):
    def init(self, size=1, *args, **kwargs):
       Enum.init(self, size, (False, True), *args, **kwargs)


class Unit:
    factor = 1
    constant = 0
    unit = ''
    invalid = None

    def __str__(self):
        if self == self.invalid:
            return '\"INVALID ({})\"'.format(self.invalid)
        return '\"{} {}\"'.format(self.factor*self + self.constant, self.unit)
