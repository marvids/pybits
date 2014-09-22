#!/usr/bin/python

import unittest
import json
from pyproto import *

class TestBitProtocolParser(unittest.TestCase):
    def testSequence(self):
        msg = Sequence(Bits('f1', 4))
        self.unserialize(msg, '0x34', '{"f1": 3}')

    def testPad(self):
        msg = Sequence(Pad(4), Bits('f1', 4))
        self.unserialize(msg, '0xf8', '{"f1": 8}')

    def testChoice(self):
        msg = Choice(4, {4: Sequence(Bits('f1', 4)), 5: Sequence(Bits('f2', 4))})
        self.unserialize(msg, '0x48', '{"f1": 8}')
        self.unserialize(msg, '0x52', '{"f2": 2}')

    def testRepeat(self):
        msg = Repeat(Sequence(Bits('f1', 4)))
        self.unserialize(msg, '0x48', '[{"f1": 4}, {"f1": 8}]')

    def testConcatSequences(self):
        msg1 = Sequence(Bits('f1', 4))
        msg2 = Sequence(Bits('f2', 4))
        msg = msg1 + msg2
        self.unserialize(msg, '0x87', '{"f1": 8, "f2": 7}')

    def testConverterArgs(self):
        def convert(value, factor, offset):
            return value*factor + offset
        msg = Sequence(Bits('f1', 8, convert, 10, 5))
        self.unserialize(msg, '0x05', '{"f1": 55}')

    def testEnumDict(self):
        msg = Sequence(Enum('flag', 1, {0: 'FALSE', 1: 'TRUE'}))
        self.unserialize(msg, '0x80', '{"flag": "TRUE"}')
        self.unserialize(msg, '0x00', '{"flag": "FALSE"}')

    def testEnumTuple(self):
        msg = Sequence(Enum('flag', 8, ('FALSE', 'TRUE'), offset=1))
        self.unserialize(msg, '0x02', '{"flag": "TRUE"}')
        self.unserialize(msg, '0x01', '{"flag": "FALSE"}')

    def testUint(self):
        msg = Uint(8)
        self.unserialize(msg, '0xff', '255')

    def testInt(self):
        msg = Int(8)
        self.unserialize(msg, '0xff', '-1')

    def testComposite(self):
        msg = Sequence(
                Bits('f1', 8),
                Pad(8),
                Sequence('f2', Bits('g1', 4)),
                Repeat('f3', Choice(4, {6: Sequence(Bits('a1', 8), Bits('a2', 8)),
                                        7: Sequence(Bits('a3', 4), Bits('a4', 4))})
                )
            )
        self.unserialize(msg,
                '0x11ff265434726',
                '{"f1": 17, "f2": {"g1": 2}, "f3": [{"a1": 84, "a2": 52}, {"a3": 2, "a4": 6}]}')

    def unserialize(self, msg, data, expected):
        self.assertEqual(json.dumps(msg.unserialize(data)), expected)

if __name__ == '__main__':
    unittest.main()
