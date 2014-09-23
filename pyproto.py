#!/usr/bin/python

import json
import collections
from bitstring import ConstBitStream


try:
  basestring
except NameError:
  basestring = str


class Message(collections.OrderedDict):
    def __init__(self, name=None, *args, **kwargs):
        super(Message, self).__init__(*args, **kwargs)
        self.name = name

    def __str__(self):
        s = ''
        if self.name:
            s += self.name + ' = '
        return s + json.dumps(self, indent=4)


class Field:
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

    def init(self):
        pass

    def unserialize(self, data):
        return self.parse(ConstBitStream(data))


class Sequence(Field):
    def init(self, *tokens):
        self.tokens = tokens

    def parse(self, stream):
        message = Message(self.name)
        for token in self.tokens:
            value = token.parse(stream)
            if token.name:
                message[token.name] = value
            elif value:
                message.update(value)
        return message


    def __add__(self, other):
        tokens = self.tokens + other.tokens
        return Sequence(*tokens)


class Choice(Field):
    def init(self, fmt, alternatives):
        self.token = Bits(fmt)
        self.alternatives = alternatives

    def parse(self, stream):
        select = self.token.parse(stream)
        token = self.alternatives[select]
        value = token.parse(stream)
        if token.name:
            return Message(self.name, {token.name: value})
        return value


class Repeat(Field):
    def init(self, sequence):
        self.sequence = sequence

    def parse(self, stream):
        l = []
        while stream.pos < stream.len:
            l.append(self.sequence.parse(stream))
        return l


class Bits(Field):
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
        self.fmt = str(size)

    def parse(self, stream):
        Bits.parse(self, stream)


class Uint(Bits):
    pass


class Int(Bits):
    def init(self, size, *args, **kwargs):
        fmt = 'int:{}'.format(size)
        Bits.init(self, fmt, *args, **kwargs)


class Unit:
    factor = 1
    constant = 0
    unit = ''

    def __str__(self):
        return '\"{} {}\"'.format(self.factor*self + self.constant, self.unit)
