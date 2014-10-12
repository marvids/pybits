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


class ReferenceException(Exception):
    pass


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
    debug = False

    def __init__(self, *args, **kwargs):
        self.name = None
        if len(args) > 0 and (isinstance(args[0], basestring) or not args[0]):
            self.name = args[0]
            args = args[1:]

        self.options = {}
        self.options['conv'] = []
        if 'conv' in kwargs:
            self.options['conv'] = [kwargs['conv']]
            del kwargs['conv']

        self.args = args
        self.kwargs = kwargs
        self.init(*args, **kwargs)

    def __call__(self, name=None):
        c = copy.copy(self)
        c.name = name
        return c

    def init(self, *args, **kwargs):
        pass

    def addConverter(self, conv):
        self.options['conv'] += [conv]

    def getOption(self, option):
        if option in self.options:
            return self.options[option]
        return None

    def parse(self, stream, parent):
        if self.debug:
            print('{}({})\n\t{}'.format(self.__class__.__name__, self.name, stream[stream.pos:]))
        field =  self._parse(stream, parent)
        for converter in self.getOption('conv'):
            field = converter(field)
        return field

    def deserialize(self, data, debug=False):
        Token.debug = debug
        return self.parse(ConstBitStream(data), None)


class Sequence(Token):
    def _parse(self, stream, parent):
        field = DictField(self.name, parent)
        for token in self.args:
            value = token.parse(stream, field)
            if token.name:
                field[token.name] = value
            elif value:
                field.update(value)

        nameFrom = self.getOption('nameFrom')
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

    def _parse(self, stream, parent):
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

        self.sequence = Sequence(*args[0:])

    def _parse(self, stream, parent):
        n = self.getNumberOfItems(stream, parent)
        field = ListField()

        while stream.pos < stream.len and n != 0:
            field.append(self.sequence.parse(stream, field))
            n -= 1
        return field


class Bits(Token):
    def init(self, fmt, conv=None):
        if not isinstance(fmt, Fmt):
            self.fmt = Fmt(fmt)
        else:
            self.fmt = fmt
        if conv:
            self.addConverter(conv)

    def _parse(self, stream, parent):
        return stream.read(self.fmt.s)


class StrArg(object):
    def __init__(self, s):
        self.s = str(s)


class Ref(StrArg):
    pass


class Fmt(StrArg):
    pass


class Pad(Bits):
    def __init__(self, size):
        super(Pad, self).__init__(size)

    def _parse(self, stream, parent):
        super(Pad, self)._parse(stream, parent)


class Enum(Bits):
    def init(self, fmt, enum, offset=0):
        self.enum = enum
        self.offset = offset
        self.addConverter(self)
        Bits.init(self, fmt)

    def __call__(self, value):
        def isUndefined(index, enum):
            if isinstance(enum, dict) and index not in enum:
                return True
            if index >= len(enum) or index < 0:
                return True
            return False

        index = value - self.offset
        if isUndefined(index, self.enum):
            result = '_UNDEFINED_({})'.format(value)
        else:
            result = self.enum[index]
        return result



class BitMask(Bits):
    def init(self, fmt, mask):
        def convertToBitMask(value, mask):
            field = ListField()
            index = 0
            while value:
                if value & 1:
                    field.append(mask[index])
                value = value >> 1
                index += 1
            return field

        Bits.init(self, fmt, convertToBitMask, mask)


class Uint(Bits):
    pass


class Int(Bits):
    def init(self, size, *args, **kwargs):
        fmt = Fmt('int:{}'.format(size))
        Bits.init(self, fmt, *args, **kwargs)


class Bool(Enum):
    def init(self, size=1, *args, **kwargs):
        self.addConverter(self)
        Bits.init(self, size)

    def __call__(self, value):
        return value != 0


class String(Bits):
    def init(self, size):
        fmt = Fmt('bytes:{}'.format(size))
        Bits.init(self, fmt)


class FieldType(object):
    factor = 1
    constant = 0
    unit = ''
    valueTable = None

    def __str__(self):
        if self.valueTable:
            try:
                if self in self.valueTable:
                    return str(self.valueTable[self])
            except TypeError:
                return self.valueTable(self)
        value = self.factor*self + self.constant
        if self.unit:
            return '{} {}'.format(value, self.unit)
        return str(value)


def Squash(field):
    squashed = DictField(field.name, field.parent)
    for item in field:
        squashed.update(item)
    return squashed


class GetName(object):
    def __init__(self, fieldName, conv=None):
        self.fieldName = fieldName
        self.conv = conv

    def __call__(self, field):
        field.name = self.conv(field[self.fieldName])
        return field

