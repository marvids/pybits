#!/usr/bin/python

import collections
from bitstring import ConstBitStream


class Sequence:
    def __init__(self, *args):
        self.args = args

    def parse(self, stream):
        message = collections.OrderedDict()
        for name, field in self.args:
            value = field.parse(stream)
            if name is not None:
                message[name] = value
        return message

    def __add__(self, other):
        args = self.args + other.args
        return Sequence(*args)


class Choice:
    def __init__(self, size, selector):
        self.token = Bits(size)
        self.selector = selector

    def parse(self, stream):
        value = self.token.parse(stream)
        return self.selector[value].parse(stream)


class Repeat:
    def __init__(self, sequence):
        self.sequence = sequence

    def parse(self, stream):
        l = []
        while stream.pos < stream.len:
            l.append(self.sequence.parse(stream))
        return l


class Bits:
    def __init__(self, fmt, converter=None):
        if isinstance(fmt, int):
            self.fmt = str(fmt)
        else:
            self.fmt = fmt
        self.converter = converter

    def parse(self, stream):
        val = stream.read(self.fmt)
        if self.converter:
            return self.converter(val)
        else:
            return val


def Pad(size):
    return (None, Bits(size))


class Unit:
    factor = 1
    constant = 0
    unit = ''

    def __str__(self):
        return '{} {}'.format(self.factor*self + self.constant, self.unit)
