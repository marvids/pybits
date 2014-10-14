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


class ReferenceError(Exception):
    pass


class ConverterError(Exception):
    pass


class OptionError(Exception):
    pass


class Ref(object):
    def __init__(self, ref):
        self.ref = ref


class Fmt(object):
    def __init__(self, fmt):
        self.fmt = str(fmt)


class Options(object):
    def __init__(self):
        self.options = {}

    def addOption(self, name, default):
        self.options[name] = default

    def initOptions(self, options):
        unknown = [o for o in options if o not in self.options]
        if unknown:
            raise OptionError("Unknown option(s): {}".format(unknown))
        self.options.update(options)

    def appendOption(self, option, value):
        self.options[option] += [value]

    def getOption(self, option):
        return self.options[option]


class Field(object):
    indent = 4

    def __init__(self, name=None, parent=None):
        self.name = name
        self.parent = parent

    def __str__(self):
        s = ''
        if self.name:
            s += self.name + ' = '
        return s + json.dumps(self, indent=self.indent)

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

    def prepend(self, key, value):
        items = self.items()
        self.clear()
        self.update([(key, value)] + items)

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


class Token(Options):
    debug = False

    def __init__(self, *args, **options):
        super(Token, self).__init__()
        self.addOption('conv', [])

        self.name = None
        if len(args) > 0 and (isinstance(args[0], basestring) or not args[0]):
            self.name = args[0]
            args = args[1:]
        self.init(*args)
        self.initOptions(options)

    def __call__(self, name=None):
        c = copy.copy(self)
        c.name = name
        return c

    def parse(self, stream, parent):
        if self.debug:
            print('{}({})\n\t{}'.format(self.__class__.__name__, self.name, stream[stream.pos:]))
        field =  self._parse(stream, parent)

        converters = self.getOption('conv')
        if not isinstance(converters, list):
            converters = [converters]
        for converter in converters:
            field = converter(field)

        return field

    def deserialize(self, data, debug=False):
        Token.debug = debug
        return self.parse(ConstBitStream(data), None)


class Sequence(Token):
    def init(self, *tokens):
        self.tokens = tokens

    def _parse(self, stream, parent):
        field = DictField(self.name, parent)
        for token in self.tokens:
            value = token.parse(stream, field)
            if token.name:
                field[token.name] = value
            elif value:
                field.update(value)
        return field


    def __add__(self, other):
        tokens = self.tokens + other.tokens
        options = self.options
        options.update(other.options)
        return Sequence(*tokens, **options)


class Choice(Token):
    def init(self, selector, alternatives):
        selectorMap = {Ref: lambda s, p: p.findRef(self.selector.ref)}
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
    def init(self, *args):
        nMap = {Fmt: lambda s, p: Bits(self.name, self.n).parse(s, p),
                int: lambda s, p: self.n,
                Ref: lambda s, p: p.findRef(self.n.ref)}
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
            self.appendOption('conv', conv)

    def _parse(self, stream, parent):
        return stream.read(self.fmt.fmt)


class Pad(Bits):
    def _parse(self, *args):
        super(Pad, self)._parse(*args)


class Enum(Bits):
    def init(self, fmt, enum):
        self.enum = enum
        self.addOption('offset', 0)
        Bits.init(self, fmt, self.toEnum)

    def toEnum(self, value):
        index = value - self.getOption('offset')
        try:
            result = self.enum[index]
        except:
            result = '_UNDEFINED_({})'.format(value)

        return result


class BitMask(Bits):
    def init(self, fmt, mask):
        self.mask = mask
        Bits.init(self, fmt, self.toBitmask)

    def toBitmask(self, value):
        field = ListField()
        index = 0
        while value:
            if value & 1:
                field.append(self.mask[index])
            value = value >> 1
            index += 1
        return field


class Uint(Bits):
    pass


class Int(Bits):
    def init(self, size, *args):
        fmt = Fmt('int:{}'.format(size))
        Bits.init(self, fmt, *args)


class Bool(Enum):
    def init(self, size=1, *args):
        self.appendOption('conv', self.toBool)
        Bits.init(self, size)

    def toBool(self, value):
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
        duplicates = [i for i in item.keys() if i in squashed.keys()]
        if duplicates:
            raise ConverterError("The field {} cannot be squashed."
                "The following fields will be lost: {}".format(field, duplicates))
        squashed.update(item)
    return squashed


class GetName(Options):
    def __init__(self, ref, conv=None, **options):
        super(GetName, self).__init__()
        self.ref = ref
        self.addOption('remove', True)
        self.addOption('conv', conv)
        self.initOptions(options)

    def __call__(self, field):
        name = field[self.ref]
        conv = self.getOption('conv')
        if conv:
            name = conv(name)
        if self.getOption('remove'):
            del field[self.ref]
        return DictField(None, field.parent, {name: field})


class AddField(Options):
    def __init__(self, name, ref, conv=None, **options):
        super(AddField, self).__init__()
        self.name = name
        self.ref = ref
        self.addOption('conv', conv)
        self.addOption('onTop', False)
        self.initOptions(options)

    def __call__(self, field):
        value = field[self.ref]
        conv = self.getOption('conv')
        if conv:
            value = conv(value)
        if self.getOption('onTop'):
            field.prepend(self.name, value)
        else:
            field[self.name] = value
        return field
