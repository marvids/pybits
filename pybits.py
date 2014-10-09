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


def debug(f):
    def debug_parsing(self, stream, parent):
        #print('{}({})\n\t{}'.format(self.__class__.__name__, self.name, stream[stream.pos:]))
        return f(self, stream, parent)
    return debug_parsing


class Field(object):
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

    def __dir__(self):
        return self.keys()


class ListField(Field, list):
    def __init__(self, name=None, parent=None, *args, **kwargs):
        Field.__init__(self, name, parent)
        list.__init__(self, *args, **kwargs)


class Token(object):
    def __init__(self, *args, **kwargs):
        self.name = None
        if isinstance(args[0], basestring) or not args[0]:
            self.name = args[0]
            args = args[1:]
        self.init(*args, **kwargs)

    def __call__(self, name=None):
        c = copy.copy(self)
        c.name = name
        return c

    def init(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def unserialize(self, data):
        return self.parse(ConstBitStream(data), None)


class Sequence(Token):
    @debug
    def parse(self, stream, parent):
        field = DictField(self.name, parent)
        for token in self.args:
            value = token.parse(stream, field)
            if token.name:
                field[token.name] = value
            elif value:
                field.update(value)
        if 'nameFrom' in self.kwargs:
            name = field[self.kwargs['nameFrom']]
            if 'removeNameFromField' in self.kwargs and self.kwargs['removeNameFromField']:
                del field[self.kwargs['nameFrom']]
            if 'nameFromConversion' in self.kwargs:
                name = self.kwargs['nameFromConversion'](name)
            else:
                name = str(name)
            field = DictField(None, parent, {name: field})

        return field


    def __add__(self, other):
        args = self.args + other.args
        kwargs = self.kwargs
        kwargs.update(other.kwargs)
        return Sequence(*args, **kwargs)


class Choice(Token):
    def init(self, selector, alternatives):
        selectorMap = {Ref: lambda s, p: p.findRef(self.selector.s)}

        try:
            self.getSelector = selectorMap[selector.__class__]
        except KeyError:
            self.getSelector = lambda s, p: Bits(self.name, self.selector).parse(s, p)

        self.alternatives= alternatives
        self.selector = selector

    @debug
    def parse(self, stream, parent):
        select = self.getSelector(stream, parent)
        token = self.alternatives[select]
        try:
            value = token.parse(stream, parent)
            if token.name:
                return DictField(self.name, parent, {token.name: value})
        except AttributeError:
            value = token
        return value


class Repeat(Token):
    def init(self, *args, **kwargs):
        nMap = {Fmt: lambda s, p: Bits(self.name, self.n).parse(s, p),
                int: lambda s, p: self.n,
                Ref: lambda s, p: p.findRef(self.n.s)}
        try:
            self.getNumberOfItems = nMap[args[0].__class__]
            self.n = args[0]
            args = args[1:]
        except KeyError:
            self.getNumberOfItems = lambda stream, parent: -1

        self.squash = False
        if 'squash' in kwargs:
            self.squash = kwargs['squash']
        self.sequence = Sequence(*args[0:])

    @debug
    def parse(self, stream, parent):
        n = self.getNumberOfItems(stream, parent)

        if self.squash:
            field = DictField(self.name, parent)
            append = lambda d: field.update(d)
        else:
            field = ListField()
            append = lambda d: field.append(d)

        while stream.pos < stream.len and n != 0:
            append(self.sequence.parse(stream, field))
            n -= 1
        return field


class Bits(Token):
    def init(self, fmt, converter=None, *args, **kwargs):
        if not isinstance(fmt, Fmt):
            self.fmt = Fmt(fmt)
        else:
            self.fmt = fmt

        self.converter = converter
        self.converter_args = args
        self.converter_kwargs = kwargs

    @debug
    def parse(self, stream, parent):
        val = stream.read(self.fmt.s)
        if self.converter:
            return self.converter(val, *self.converter_args, **self.converter_kwargs)
        else:
            return val


class StrArg(object):
    def __init__(self, s):
        self.s = str(s)


class Ref(StrArg):
    pass


class Fmt(StrArg):
    pass


class Pad(Bits):
    def __init__(self, size):
        Bits.__init__(self, size)

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
        fmt = Fmt('int:{}'.format(size))
        Bits.init(self, fmt, *args, **kwargs)


class Bool(Enum):
    def init(self, size=1, *args, **kwargs):
       Enum.init(self, size, (False, True), *args, **kwargs)


class Type(object):
    factor = 1
    constant = 0
    unit = ''
    valueStr = None

    def __str__(self):
        if self.valueStr:
            try:
                if self in self.valueStr:
                    return str(self.valueStr[self])
            except TypeError:
                return self.valueStr(self)
        value = self.factor*self + self.constant
        if self.unit:
            return '{} {}'.format(value, self.unit)
        return str(value)
