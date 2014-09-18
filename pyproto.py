#!/usr/bin/python

import collections

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


class Token:
    def __init__(self, size, f=None):
        self.size = size
        self.f = f

    def parse(self, stream):
        if self.f:
            return self.f(self.size)
        else:
            return self.size - 1


class Choice:
    def __init__(self, size, selector):
        self.token = Token(size)
        self.selector = selector

    def parse(self, stream):
        value = self.token.parse(stream)
        return self.selector[value].parse(stream)


class Repeat:
    def __init__(self, sequence):
        self.sequence = sequence


if __name__ == '__main__':
    alt1 = Sequence(('alt1', Token(8)))
    alt2 = Sequence(('alt2', Token(8)))

    message = Sequence(
        ('field1', Token(1)),
        (None, Token(3)),
        ('field2', Token(7, hex)),
        ('field3', Choice(1, {0: alt1, 1: alt2}))
    )

    import json
    print(json.dumps(message.parse(1), indent=4))
