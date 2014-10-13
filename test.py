#!/usr/bin/python

import unittest
import json
from pybits import *

class TestBits(unittest.TestCase):
    def testGetName(self):
        msg = Sequence(Bits('f1', 8), conv=GetName('f1', conv=hex, remove=False))
        self.deserialize(msg, '0x10', '{"0x10": {"f1": 16}}')

    def testSquash(self):
        msg = Repeat(Choice(8, {1: Bits('f1', 8), 2: Bits('f2', 8)}), conv=Squash)
        self.deserialize(msg, '0x01100214', '{"f1": 16, "f2": 20}')

    def testSquashException(self):
        msg = Repeat(Choice(8, {1: Bits('f1', 8), 2: Bits('f1', 8)}), conv=Squash)
        self.assertRaises(ConverterException, msg.deserialize, '0x01100214')

    def testSequence(self):
        msg = Sequence(Bits('f1', 4))
        self.deserialize(msg, '0x34', '{"f1": 3}')

    def testPad(self):
        msg = Sequence(Pad(4), Bits('f1', 4))
        self.deserialize(msg, '0xf8', '{"f1": 8}')

    def testChoice(self):
        msg = Choice(4, {4: Sequence(Bits('f1', 4)), 5: Sequence(Bits('f2', 4))})
        self.deserialize(msg, '0x48', '{"f1": 8}')
        self.deserialize(msg, '0x52', '{"f2": 2}')

    def testChoiceSiblingReference(self):
        msg = Sequence(Bits('selection', 8), Choice(Ref('selection'), {2: Bits('b', 8), 4: Bits('c', 4)}))
        self.deserialize(msg, '0x0234', '{"selection": 2, "b": 52}')
        self.deserialize(msg, '0x0434', '{"selection": 4, "c": 3}')

    def testChoiceParentReference(self):
        msg = Sequence(None,
                Sequence('other', Bits('selection', 8)),
                Sequence(None,
                        Choice(Ref('../other/selection'), {2: Bits('b', 8), 4: Bits('c', 4)})
                    )
                )
        self.deserialize(msg, '0x0234', '{"other": {"selection": 2}, "b": 52}')

    def testRepeatForever(self):
        msg = Repeat(Sequence(Bits('f1', 4)))
        self.deserialize(msg, '0x483', '[{"f1": 4}, {"f1": 8}, {"f1": 3}]')

    def testRepeatParseNumberOfTimes(self):
        msg = Repeat(Fmt(8), Sequence(Bits('f1', 4)))
        self.deserialize(msg, '0x02483', '[{"f1": 4}, {"f1": 8}]')

    def testRepeatNumberOfTimes(self):
        msg = Repeat(2, Sequence(Bits('f1', 4)))
        self.deserialize(msg, '0x483', '[{"f1": 4}, {"f1": 8}]')

    def testRepeatReference(self):
        msg = Sequence(Bits('numOfTimes', 4), Repeat('list', Ref('numOfTimes'), Sequence(Bits('f1', 4))))
        self.deserialize(msg, '0x2483', '{"numOfTimes": 2, "list": [{"f1": 4}, {"f1": 8}]}')

    def testRepeatSequence(self):
        msg = Repeat(2, Bits('f1', 4), Bits('f2', 4))
        self.deserialize(msg, '0x1234', '[{"f1": 1, "f2": 2}, {"f1": 3, "f2": 4}]')

    def testConcatSequences(self):
        msg1 = Sequence(Bits('f1', 4))
        msg2 = Sequence(Bits('f2', 4))
        msg = msg1 + msg2
        self.deserialize(msg, '0x87', '{"f1": 8, "f2": 7}')

    def testConverterArgs(self):
        def convert(value):
            return value*2
        msg = Sequence(Bits('f1', 8, convert))
        self.deserialize(msg, '0x05', '{"f1": 10}')

    def testEnumDict(self):
        msg = Sequence(Enum('flag', 1, {0: 'FALSE', 1: 'TRUE'}))
        self.deserialize(msg, '0x80', '{"flag": "TRUE"}')
        self.deserialize(msg, '0x00', '{"flag": "FALSE"}')

    def testEnumTuple(self):
        msg = Sequence(Enum('flag', 8, ('FALSE', 'TRUE'), 1))
        self.deserialize(msg, '0x02', '{"flag": "TRUE"}')
        self.deserialize(msg, '0x01', '{"flag": "FALSE"}')

    def testUint(self):
        msg = Uint(8)
        self.deserialize(msg, '0xff', '255')

    def testInt(self):
        msg = Int(8)
        self.deserialize(msg, '0xff', '-1')

    def testBool(self):
        msg = Bool()
        self.deserialize(msg, '0x80', 'true')
        self.deserialize(msg, '0x00', 'false')

    def testComposite(self):
        msg = Sequence(
                Bits('f1', 8),
                Pad(8),
                Sequence('f2', Bits('g1', 4)),
                Repeat('f3', Choice(4, {6: Sequence(Bits('a1', 8), Bits('a2', 8)),
                                        7: Sequence(Bits('a3', 4), Bits('a4', 4))})
                )
            )
        self.deserialize(msg,
                '0x11ff265434726',
                '{"f1": 17, "f2": {"g1": 2}, "f3": [{"a1": 84, "a2": 52}, {"a3": 2, "a4": 6}]}')

    def testAccess(self):
        msg = Sequence(Bits('f1', 4))
        data = msg.deserialize('0x34')
        self.assertEqual(data.f1, 3)

    def testHierarchy(self):
        msg = Sequence(Sequence('child1', Bits('b', 4)), Sequence('child2', Bits('b', 4)))
        data = msg.deserialize('0x34')
        self.assertEqual(data.child1.parent.child2.b, 4)

    def testTypeValueTable(self):
        class TestType(FieldType, int):
            valueTable = {255: "INVALID"}
        msg = Bits(8, TestType)
        self.assertEqual(str(msg.deserialize('0x10')), '16')
        self.assertEqual(str(msg.deserialize('0xff')), 'INVALID')

    def deserialize(self, msg, data, expected):
        self.assertEqual(json.dumps(msg.deserialize(data)), expected)

if __name__ == '__main__':
    unittest.main()
