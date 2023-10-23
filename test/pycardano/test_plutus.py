import copy
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from test.pycardano.util import check_two_way_cbor
from typing import Dict, List, Union

import pytest
from cbor2 import CBORTag

from pycardano.exception import DeserializeException
from pycardano.plutus import (
    COST_MODELS,
    ExecutionUnits,
    PlutusData,
    RawPlutusData,
    Redeemer,
    RedeemerTag,
    plutus_script_hash,
    id_map,
    Datum,
    Unit,
)
from pycardano.serialization import IndefiniteList, RawCBOR, ByteString


@dataclass
class MyTest(PlutusData):
    CONSTR_ID = 130

    a: int
    b: bytes
    c: IndefiniteList
    d: dict


@dataclass
class BigTest(PlutusData):
    CONSTR_ID = 8

    test: MyTest


@dataclass
class LargestTest(PlutusData):
    CONSTR_ID = 9


@dataclass
class DictTest(PlutusData):
    CONSTR_ID = 3

    a: Dict[int, LargestTest]


@dataclass
class ListTest(PlutusData):
    CONSTR_ID = 0
    a: List[LargestTest]


@dataclass
class VestingParam(PlutusData):
    CONSTR_ID = 1

    beneficiary: bytes
    deadline: int
    testa: Union[BigTest, LargestTest]
    testb: Union[BigTest, LargestTest]


@dataclass
class MyRedeemer(Redeemer):
    data: MyTest


def test_plutus_data():
    """Ground truth of this test is generated by test/resources/haskell/PlutusData. See its README for more details."""
    key_hash = bytes.fromhex("c2ff616e11299d9094ce0a7eb5b7284b705147a822f4ffbd471f971a")
    deadline = 1643235300000
    testa = BigTest(MyTest(123, b"1234", IndefiniteList([4, 5, 6]), {1: b"1", 2: b"2"}))
    testb = LargestTest()

    my_vesting = VestingParam(
        beneficiary=key_hash, deadline=deadline, testa=testa, testb=testb
    )
    assert (
        "d87a9f581cc2ff616e11299d9094ce0a7eb5b7284b705147a822f4ffbd471f971a1b0000017e9"
        "874d2a0d905019fd8668218829f187b44313233349f040506ffa2014131024132ffffd9050280ff"
        == my_vesting.to_cbor_hex()
    )
    check_two_way_cbor(my_vesting)


def test_plutus_data_json():
    key_hash = bytes.fromhex("c2ff616e11299d9094ce0a7eb5b7284b705147a822f4ffbd471f971a")
    deadline = 1643235300000
    testa = BigTest(MyTest(123, b"1234", IndefiniteList([4, 5, 6]), {1: b"1", 2: b"2"}))
    testb = LargestTest()

    my_vesting = VestingParam(
        beneficiary=key_hash, deadline=deadline, testa=testa, testb=testb
    )

    encoded_json = my_vesting.to_json(separators=(",", ":"))

    assert (
        '{"constructor":1,"fields":[{"bytes":"c2ff616e11299d9094ce0a7eb5b7284b705147a822f4ffbd471f971a"},'
        '{"int":1643235300000},{"constructor":8,"fields":[{"constructor":130,"fields":[{"int":123},'
        '{"bytes":"31323334"},{"list":[{"int":4},{"int":5},{"int":6}]},{"map":[{"v":{"bytes":"31"},'
        '"k":{"int":1}},{"v":{"bytes":"32"},"k":{"int":2}}]}]}]},{"constructor":9,"fields":[]}]}'
        == encoded_json
    )

    assert my_vesting == VestingParam.from_json(encoded_json)


def test_plutus_data_json_list():
    test = ListTest([LargestTest(), LargestTest()])
    encoded_json = test.to_json(separators=(",", ":"))

    assert (
        '{"constructor":0,"fields":[{"list":[{"constructor":9,"fields":[]},{"constructor":9,"fields":[]}]}]}'
        == encoded_json
    )

    assert test == ListTest.from_json(encoded_json)


def test_plutus_data_cbor_list():
    test = ListTest([LargestTest(), LargestTest()])

    encoded_cbor = test.to_cbor_hex()

    assert "d8799f82d9050280d9050280ff" == encoded_cbor

    assert test == ListTest.from_cbor(encoded_cbor)


def test_plutus_data_json_dict():
    test = DictTest({0: LargestTest(), 1: LargestTest()})

    encoded_json = test.to_json(separators=(",", ":"))

    assert (
        '{"constructor":3,"fields":[{"map":[{"v":{"constructor":9,"fields":[]},"k":{"int":0}},{"v":{"constructor":9,"fields":[]},"k":{"int":1}}]}]}'
        == encoded_json
    )

    assert test == DictTest.from_json(encoded_json)


def test_plutus_data_cbor_dict():
    test = DictTest({0: LargestTest(), 1: LargestTest()})

    encoded_cbor = test.to_cbor_hex()

    assert "d87c9fa200d905028001d9050280ff" == encoded_cbor

    assert test == DictTest.from_cbor(encoded_cbor)


def test_plutus_data_to_json_wrong_type():
    test = MyTest(123, b"1234", IndefiniteList([4, 5, 6]), {1: b"1", 2: b"2"})
    test.a = "123"
    with pytest.raises(TypeError):
        test.to_json()


def test_plutus_data_from_json_wrong_constructor():
    test = (
        '{"constructor": 129, "fields": [{"int": 123}, {"bytes": "31323334"}, '
        '{"list": [{"int": 4}, {"int": 5}, {"int": 6}]}, {"map": [{"v": {"bytes": "31"}, '
        '"k": {"int": 1}}, {"v": {"bytes": "32"}, "k": {"int": 2}}]}]}'
    )
    with pytest.raises(DeserializeException):
        MyTest.from_json(test)

    test2 = (
        '{"constructor":1,"fields":[{"bytes":"c2ff616e11299d9094ce0a7eb5b7284b705147a822f4ffbd471f971a"},'
        '{"int":1643235300000},{"constructor":22,"fields":[{"constructor":130,"fields":[{"int":123},'
        '{"bytes":"31323334"},{"list":[{"int":4},{"int":5},{"int":6}]},{"map":[{"v":{"bytes":"31"},'
        '"k":{"int":1}},{"v":{"bytes":"32"},"k":{"int":2}}]}]}]},{"constructor":23,"fields":[]}]}'
    )
    with pytest.raises(DeserializeException):
        VestingParam.from_json(test2)


def test_plutus_data_from_json_wrong_data_structure():
    test = (
        '{"constructor": 130, "fields": [{"int": 123}, {"bytes": "31323334"}, '
        '{"wrong_list": [{"int": 4}, {"int": 5}, {"int": 6}]}, {"map": [{"v": {"bytes": "31"}, '
        '"k": {"int": 1}}, {"v": {"bytes": "32"}, "k": {"int": 2}}]}]}'
    )
    with pytest.raises(DeserializeException):
        MyTest.from_json(test)


def test_plutus_data_from_json_wrong_data_structure_type():
    test = (
        '[{"constructor": 130, "fields": [{"int": 123}, {"bytes": "31323334"}, '
        '{"list": [{"int": 4}, {"int": 5}, {"int": 6}]}, {"map": [{"v": {"bytes": "31"}, '
        '"k": {"int": 1}}, {"v": {"bytes": "32"}, "k": {"int": 2}}]}]}]'
    )
    with pytest.raises(TypeError):
        MyTest.from_json(test)


def test_plutus_data_hash():
    assert (
        "923918e403bf43c34b4ef6b48eb2ee04babed17320d8d1b9ff9ad086e86f44ec"
        == Unit().hash().payload.hex()
    )


def test_execution_units_bool():
    assert ExecutionUnits(
        1000000, 1000000
    ), "ExecutionUnits should be true when its value is not 0"
    assert not ExecutionUnits(
        0, 0
    ), "ExecutionUnits should be false when its value is 0"


def test_redeemer():
    data = MyTest(123, b"234", IndefiniteList([4, 5, 6]), {1: b"1", 2: b"2"})
    redeemer = MyRedeemer(data, ExecutionUnits(1000000, 1000000))
    redeemer.tag = RedeemerTag.SPEND
    assert (
        "840000d8668218829f187b433233349f040506ffa2014131024132ff821a000f42401a000f4240"
        == redeemer.to_cbor_hex()
    )
    check_two_way_cbor(redeemer)


def test_redeemer_empty_datum():
    data = MyTest(123, b"234", IndefiniteList([]), {1: b"1", 2: b"2"})
    redeemer = MyRedeemer(data, ExecutionUnits(1000000, 1000000))
    redeemer.tag = RedeemerTag.SPEND
    assert (
        "840000d8668218829f187b433233349fffa2014131024132ff821a000f42401a000f4240"
        == redeemer.to_cbor_hex()
    )
    check_two_way_cbor(redeemer)


def test_cost_model():
    assert (
        "a141005901d59f1a000302590001011a00060bc719026d00011a000249f01903e800011"
        "a000249f018201a0025cea81971f70419744d186419744d186419744d186419744d1864"
        "19744d186419744d18641864186419744d18641a000249f018201a000249f018201a000"
        "249f018201a000249f01903e800011a000249f018201a000249f01903e800081a000242"
        "201a00067e2318760001011a000249f01903e800081a000249f01a0001b79818f7011a0"
        "00249f0192710011a0002155e19052e011903e81a000249f01903e8011a000249f01820"
        "1a000249f018201a000249f0182001011a000249f0011a000249f0041a000194af18f80"
        "11a000194af18f8011a0002377c190556011a0002bdea1901f1011a000249f018201a00"
        "0249f018201a000249f018201a000249f018201a000249f018201a000249f018201a000"
        "242201a00067e23187600010119f04c192bd200011a000249f018201a000242201a0006"
        "7e2318760001011a000242201a00067e2318760001011a0025cea81971f704001a00014"
        "1bb041a000249f019138800011a000249f018201a000302590001011a000249f018201a"
        "000249f018201a000249f018201a000249f018201a000249f018201a000249f018201a0"
        "00249f018201a00330da70101ff" == COST_MODELS.to_cbor_hex()
    )


def test_plutus_script_hash():
    plutus_script = b"test_script"
    assert (
        "36c198e1a9d05461945c1f1db2ffb927c2dfc26dd01b59ea93b678b2"
        == plutus_script_hash(plutus_script).payload.hex()
    )


def test_raw_plutus_data():
    raw_plutus_cbor = (
        "d8799f581c23347b25deab0b28b5baa917944f212cfe833e74dd5712d"
        "6bcec54de9fd8799fd8799fd8799f581c340ebc5a2d7fdd5ad61c9461"
        "ab83a04631a1a2dd2e53dc672b57e309ffd8799fd8799fd8799f581cb"
        "c5acf6c6b031be26da4804068f5852b4f119e246d907066627a9f5fff"
        "ffffffa140d8799f00a1401a000f2ad0ffffd8799fd8799fd8799f581"
        "c70e60f3b5ea7153e0acc7a803e4401d44b8ed1bae1c7baaad1a62a72"
        "ffd8799fd8799fd8799f581c1e78aae7c90cc36d624f7b3bb6d86b526"
        "96dc84e490f343eba89005fffffffffa140d8799f00a1401a000f2ad0"
        "ffffd8799fd8799fd8799f581c23347b25deab0b28b5baa917944f212"
        "cfe833e74dd5712d6bcec54deffd8799fd8799fd8799f581c084be0e3"
        "85f956227ec1710db40e45fc355c858debea77176aa91d07ffffffffa"
        "140d8799f00a1401a004c7a20ffffffff"
    )
    raw_plutus_data = RawPlutusData.from_cbor(raw_plutus_cbor)
    assert raw_plutus_data.to_cbor_hex() == raw_plutus_cbor
    check_two_way_cbor(raw_plutus_data)


def test_clone_raw_plutus_data():
    tag = RawPlutusData(CBORTag(121, [1000]))

    cloned_tag = copy.deepcopy(tag)
    assert cloned_tag == tag
    assert cloned_tag.to_cbor_hex() == tag.to_cbor_hex()

    tag.data.value = [1001]

    assert cloned_tag != tag


def test_clone_plutus_data():
    key_hash = bytes.fromhex("c2ff616e11299d9094ce0a7eb5b7284b705147a822f4ffbd471f971a")
    deadline = 1643235300000
    testa = BigTest(MyTest(123, b"1234", IndefiniteList([4, 5, 6]), {1: b"1", 2: b"2"}))
    testb = LargestTest()
    my_vesting = VestingParam(
        beneficiary=key_hash, deadline=deadline, testa=testa, testb=testb
    )

    cloned_vesting = copy.deepcopy(my_vesting)
    assert cloned_vesting == my_vesting
    assert cloned_vesting.to_cbor_hex() == my_vesting.to_cbor_hex()

    my_vesting.deadline = 1643235300001

    assert cloned_vesting != my_vesting


def test_unique_constr_ids():
    @dataclass
    class A(PlutusData):
        pass

    @dataclass
    class B(PlutusData):
        pass

    assert (
        A.CONSTR_ID != B.CONSTR_ID
    ), "Different classes (different names) have same default constructor ID"
    B_tmp = B

    @dataclass
    class B(PlutusData):
        a: int
        b: bytes

    assert (
        B_tmp.CONSTR_ID != B.CONSTR_ID
    ), "Different classes (different fields) have same default constructor ID"

    B_tmp = B

    @dataclass
    class B(PlutusData):
        a: bytes
        b: bytes

    assert (
        B_tmp.CONSTR_ID != B.CONSTR_ID
    ), "Different classes (different field types) have same default constructor ID"


def test_deterministic_constr_ids_local():
    @dataclass
    class A(PlutusData):
        a: int
        b: bytes

    A_tmp = A

    @dataclass
    class A(PlutusData):
        a: int
        b: bytes

    assert (
        A_tmp.CONSTR_ID == A.CONSTR_ID
    ), "Same class has different default constructor ID"


def test_deterministic_constr_ids_global():
    code = """
from dataclasses import dataclass
from pycardano import PlutusData

@dataclass
class A(PlutusData):
    a: int
    b: bytes

print(A.CONSTR_ID)
"""
    tmpfile = tempfile.TemporaryFile()
    tmpfile.write(code.encode("utf8"))
    tmpfile.seek(0)
    res = subprocess.run([sys.executable], stdin=tmpfile, capture_output=True).stdout
    tmpfile.seek(0)
    res2 = subprocess.run([sys.executable], stdin=tmpfile, capture_output=True).stdout

    assert (
        res == res2
    ), "Same class has different default constructor id in two consecutive runs"


def test_id_map_supports_all():
    @dataclass
    class A(PlutusData):
        CONSTR_ID = 0
        a: int
        b: bytes
        c: List[int]

    @dataclass
    class C(PlutusData):
        x: RawPlutusData
        y: RawCBOR
        z: Datum
        w: IndefiniteList

    @dataclass
    class B(PlutusData):
        a: int
        c: A
        d: Dict[bytes, C]
        e: Union[A, C]

    s = id_map(B)
    assert (
        s
        == "cons[B](1013743048;a:int,c:cons[A](0;a:int,b:bytes,c:list<int>),d:map<bytes,cons[C](892310804;x:any,y:any,z:any,w:list)>,e:union<cons[A](0;a:int,b:bytes,c:list<int>),cons[C](892310804;x:any,y:any,z:any,w:list)>)"
    )


def test_plutus_data_long_bytes():
    @dataclass
    class A(PlutusData):
        CONSTR_ID = 0
        a: ByteString

    quote = (
        "The line separating good and evil passes ... right through every human heart."
    )

    quote_hex = (
        "d8799f5f5840546865206c696e652073657061726174696e6720676f6f6420616e64206576696c20706173736573202e2e2e207269676874207468726f7567682065766572794d2068756d616e2068656172742effff"
    )

    A_tmp = A(ByteString(quote.encode()))

    assert (
        A_tmp.to_cbor_hex() == quote_hex
    ), "Long metadata bytestring is encoded incorrectly."
