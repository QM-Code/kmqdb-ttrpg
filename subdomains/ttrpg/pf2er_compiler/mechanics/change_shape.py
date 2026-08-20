"""Compile the reviewed Monster Core Change Shape source family.

This module is deliberately compile-only.  Every direct Change Shape carrier,
related prose use, glossary rule, Player Core rule, shared producer, and local
producer is selected through one explicit ``SourceAuthorityAdapter``.  Caller
assembled source objects and caller supplied providers are not accepted.

The compiler retains exact authority receipts and the packet's
duplicate-preserving legacy source digests.  It parses the complete reviewed
41-carrier census and five related prose uses, then emits immutable artifacts
that must be revalidated through the same authority before linking or
serialization.  No registry fragment or encounter-runtime handler exists.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Callable, Literal, TypeAlias, final

from .contracts import RawSourceArray, RawSourceMember, RawSourceObject
from .source_authority import (
    RawMemberStep,
    RuleRequirement,
    SourceAuthorityAdapter,
    SourceReceipt,
    VerifiedRuleReceipt,
    VerifiedSourceSelection,
    canonical_json_bytes,
)


FAMILY_ID = "change-shape"
MECHANIC_TYPE = "change-shape"
MONSTER_CORE_SOURCE_ID = "core-mc1"
PLAYER_CORE_SOURCE_ID = "core-pc1"
CONSUMER_CENSUS_COUNT = 41
RELATED_CENSUS_COUNT = 5
REGISTRY_STATUS = "unregistered"
DIRECT_CENSUS_SHA256 = (
    "dd156fadadfed5cd10a8d82153918ef5b5e426b852e290f9cd4e9bc35c246132"
)
RELATED_CENSUS_SHA256 = (
    "2fdd46e13f7eca2ebd7349992a9cffb6612fff0e50a7cc4afd101ba422ca5963"
)
CONSUMER_REQUIREMENTS_SHA256 = (
    "2e8046fb64bc9cf61c7dd9e114270e532c83d45eb7cb4b4b012b1f54279b99f4"
)
PROVIDER_REQUIREMENTS_SHA256 = (
    "f8d942a2dd64b719873e7a247d75dc2b94d6d3911bdc489c8100dd28cffd9d97"
)
RELATED_REQUIREMENTS_SHA256 = (
    "202d04f042b2e2d1aebf0d291dae321e1ff24046eb55fb3a06ecf1397ce2b5e9"
)
COMPILED_CENSUS_SHA256 = (
    "a750bc084bbeb2f7cce72034cd9f21b95cab7693b1e0f2a29de0d3c8774fdbbe"
)
LINKED_CENSUS_SHA256 = (
    "81bf316ec623f8d7f3a9bda516c8d438e3bd13d24b9ad59412ad65486a50c7ad"
)
RELATED_OUTPUT_SHA256 = (
    "7f50f4ce9f8aaebaa0935891af6a5be2dbe3e88e64f3eb1baab0751b24ad22bc"
)

MAX_CHANGE_SHAPE_DEPTH = 32
MAX_CHANGE_SHAPE_NODES = 4_096
MAX_CHANGE_SHAPE_LINKS = 64
MAX_CHANGE_SHAPE_LINK_DEPTH = 16
MAX_CHANGE_SHAPE_TEXT_BYTES = 32_768

ChangeShapeActionCost: TypeAlias = Literal[1, 2, "free"]
ChangeShapeCohort: TypeAlias = Literal[
    "domain-default-profile",
    "bespoke-overlay",
    "explicit-form-profiles",
    "alias-producer",
    "alias",
    "shared-producer-consumer",
]


class ChangeShapeCompileError(ValueError):
    """A source or retained artifact is outside the reviewed family."""


class ChangeShapeLinkError(ValueError):
    """A reviewed Change Shape producer graph cannot be linked."""


# Direct spec fields:
# rule id, sequence, creature, locator, carrier path, selection path,
# current block/member/value/selection hashes, legacy block/member/value/
# description hashes, cohort, action cost, description shape, explicit
# glossary flag, frequency, optional (mode, producer name), extra rule IDs.
_DirectSpec = tuple[object, ...]
_DIRECT_SPECS: tuple[_DirectSpec, ...] = (
    ('change-shape-consumer:006', 6, 'Vidileth', '12.5', (('^.creature', 1),), (('!.Change Shape', 25),), '26f0610e87922e1dce5087e60380da68984cb6255515e3c719b6cf3aa676e5da', '88484437fc14ae1ff6403e9b6cf717d82927c9dd14389f880816ccf0be328aaa', '4bb4dbcd8e8ab4b46461ebf41a506b4c573db6e3508e46ee56d91a55dfe872ab', '4bb4dbcd8e8ab4b46461ebf41a506b4c573db6e3508e46ee56d91a55dfe872ab', 'c5b4cce8723d33829603bcfaced15367bd10e23645c20d12d8bcd725d44f3c32', '1ab717f08cb55dee22379d733d993a8e2482dc85eefacba8026430fb4680f792', 'b919658fb43f4b8a38da37290a56847122fab044d183bd0f6db3a9ab3ead6411', 'b165833085b6b71931134c08805a1b0cc073722b9131029efca598e6c77398ad', 'bespoke-overlay', 'free', 'string', True, 'once per round', None, ()),
    ('change-shape-consumer:007', 7, 'Cassisian', '14.3', (('^.creature', 1),), (('!.Change Shape', 25),), 'e2ca853cea042c6ee9107a0c852431be37905a434a54f65782e27fa3591fe23d', '54644b1abe471e9fcea1a1585072403bfebf9a5db66bc484ff5d467b01e48448', 'dca2c073ccf0511d66d11de6ab931281a7a0dad9d6beb107ae1aa5fad485746c', 'dca2c073ccf0511d66d11de6ab931281a7a0dad9d6beb107ae1aa5fad485746c', 'd675d52ed0512bc3a6e61919706df38135fee41d8974992785a36c046862e22f', '8014f56bb1073c6db59cd5a49b9091d993c056c4f98d0402e09e8f0aad073464', '6f427ac0159cca6083ee11470e87f548df32982fea173f18d1d597dd6b7dc827', '45f8fc5d9a59876b0dd51f6d2ffccbe4a8fc988e73b726d45a5301809056f3a9', 'domain-default-profile', 1, 'string', True, None, None, ()),
    ('change-shape-consumer:034', 34, 'Gancanagh', '33.1', (('^.creature', 2),), (('!.Change Shape', 24),), '347d42db6e7f4ae9b24ad2b6c9520bee708bb005cc35e4e585a32748fd650963', '5bf4ed392bb365aa03ec0cbdaad01a2d7f66d4e49fe28e16189e034e3e0debda', '89baf73421db5c85f4e8dc215dc51071a6387049ef0eff6e9688f757f8f5957b', '89baf73421db5c85f4e8dc215dc51071a6387049ef0eff6e9688f757f8f5957b', '8186bbdac29080d53536dc40fe43a525249c3b75eb1b507cb4ad869da2f8bd4f', 'a13eab6c6b47c9dbfdb84ab9f5106c6026d98984dacad14fb6e2ab894fc31cba', '6232ae077668e262ec30dcb8e0ab87494a2795817626a72d4e7a07eb43885e34', 'e48cc7a9b09471b95d1037db9e013d0c599072d792abeef35c897875d4fd1357', 'domain-default-profile', 1, 'string', False, None, None, ()),
    ('change-shape-consumer:039', 39, 'Barghest', '38.1', (('Barghest', 1), ('Barghest', 0), ('^.creature', 4)), (('!.Change Shape', 25),), 'cc9ebffbc8f57e3199f0c2fdf3c43bdb88ed11184c38b7477bfc5fbac1162cbc', '518f6282f2d84a1afece657fa8592ed874953beb305be7ae139b7cfe6701d3b7', 'b478965b2c12e5f0204a134157d509359c43839a5655a5d4abbd459424abadf2', 'b478965b2c12e5f0204a134157d509359c43839a5655a5d4abbd459424abadf2', 'ba35d7b8dbc1b473e9a82724740eb021a5daf89b8d02b280668392bc609b939b', 'c7af05f7a63da296beb0eff3231dc9d41ed58c87077e2291ef300dbf835fa7f3', '51b2e8e06a695f1f71e8ad4f4b3116ad479a98f7b20a971075b679a00148b442', 'd6e9ec6516440f231c263fd3771a06b6af726cbb50aa0a688b4349e15191bbf0', 'bespoke-overlay', 1, 'string', True, None, None, ()),
    ('change-shape-consumer:084', 84, 'Cacodaemon', '72.3', (('^.creature', 1),), (('!.Change Shape', 24),), '341f10a4d24391e8b3b82dd339e2eb91ba03b39fb2fb9682989abdcd538633e2', '107da178b0a26422f92175fba80ab1dc9c682605ae5e1a8ababdeaba3191a766', 'b57410d09846c53b2563bc75b9033a28d97e7953661b74b0eb46a13ed19a37fd', 'b57410d09846c53b2563bc75b9033a28d97e7953661b74b0eb46a13ed19a37fd', 'b2d77148d4964a051655a3f455561feda2e37ef14c07e305bd4b773d411d2b67', '8078532425c1b9d6e16534f93940a34de20cbcb295203abc9a3555f9e4fc6e49', 'c89e2f94cc5e250ec1b167bc49eca95f135a4721d84bdc43d0b13defdce80c0c', 'b786f434a495286d4352f6a8c5d4c5efc2d566fb1c97d49e8c74e575351256d9', 'explicit-form-profiles', 1, 'ordered-paragraph-flow', True, None, None, ()),
    ('change-shape-consumer:090', 90, 'Succubus', '78.1', (('^.creature', 2),), (('!.Change Shape', 25),), '0d7d6fe8d6121896e438dcb30060c62f93b771b363c6788bf7e64deb51552380', '8e1a2ae55cdb897a534906dbf1ea12f40fb202b363d3c12c57e3fbc5a28d6a46', 'eac25296564e1cec3b9875757c4b7d01297c7f194c0eabf34b60dbfae388206c', 'eac25296564e1cec3b9875757c4b7d01297c7f194c0eabf34b60dbfae388206c', '0e8344b71006618f9f9fa76f8719dba8895fd6567d09a3817e304f04e437c474', '9671eb36d8bd22102087ab48a1570d1eee1e5a27905e5db4f864c3bb945f08cb', '95f94113e67365baaea1eb16360d0e95490e405e54181620ccc38025ebe88179', 'f176108d538e0572bc509061baf3cc2e07c7736a5c3da9b530cbc97dca052ae3', 'domain-default-profile', 2, 'string', True, None, None, ()),
    ('change-shape-consumer:103', 103, 'Gylou', '91.2', (('^.creature', 1),), (('!.Change Shape', 25),), 'ae05f9b9d3c0819204cd912b99db4cf267749a33d616c5e2742b81014d4f3fbc', '689f9fd3487556f94f657e4082e098872333a07e18877321eda65602a86f688d', '31734a1ab596165a8ae00aff5e2a19ab42329ffdb16a2d4d8deb5831fac8dfed', '31734a1ab596165a8ae00aff5e2a19ab42329ffdb16a2d4d8deb5831fac8dfed', 'cde77b4e35c83e1f31800253f99ef194b7e45d1dbbed364f4975d4534ce9135e', '065a399e1d24288dfb20483914fc46622971a021f487e0d77177ed958d565499', '8097f3a9c84cac4733ae4a246add9330c245e3d4ae2c54c181f870867c0dace9', '09780df5123090f8f4b0136f9201f4b9af78451469d30f53939211000ddb4e72', 'domain-default-profile', 1, 'string', True, None, None, ()),
    ('change-shape-consumer:124', 124, 'Gosreg', '107.1', (('^.creature', 2),), (('!.Change Shape', 28),), 'b3fdf0e8b2cebcf5bbe10948addee22717b1b1fd28bbb16158172ba79ec4df51', '3bbe7745799b3033cf5c853fa9938e104ee2d94cf62c6e248ffae1185d3e5b06', '9c625a56e75b4d9ad22fc2d226f9bce698167255bd4474ede51f919e148ca1b3', '9c625a56e75b4d9ad22fc2d226f9bce698167255bd4474ede51f919e148ca1b3', '7129a9efcbd3006ba70758e0c1a52c7820fece3d3b3e560fa712607d26fb3ac2', 'e3863ef7bb907a3f70b60050ec6321fffab4dd920afc03bd8bba86f431c22c42', '7acc1a4acba81add5b8ba5028a6eeab10c4b162549b133d1c3b769e08e6f5138', 'b4fe383bcc47712664589d25863ae54c02eda91b626289ac092c3f431507b7a8', 'bespoke-overlay', 1, 'string', True, None, None, ()),
    ('change-shape-consumer:195', 195, 'Jann', '156.2', (('^.creature', 1),), (('!.Change Shape', 27),), '7e01471358ac34b1c4055e88e9e73c4c6ad51280bdbd76604d28fc1a631ebc6b', 'ddbd88650e5ebdf466aef4c7759ac9ce0b756e1cc5b532ffea4a4d46471d8e37', 'b4933220d4e44e4bc01725cfb6d4c21ccb97354988faa97ca78c890b9fb6ffd6', 'b4933220d4e44e4bc01725cfb6d4c21ccb97354988faa97ca78c890b9fb6ffd6', '2010228a82c56f98afeb61ce9ba04571b2b09bfc60cd811298d25fdd66eec5a5', 'cec1e19e705ffe8eb1516bbae336cb548fb00e8743addcf5cc38f44ed758228f', 'a8db4c5cc58d075386ffff18d92e973458d274b8641340f6efa46fcc390d770a', 'ea5f8522ebc2e084d30777d10411b80b273aa036f6c052cc68e5793abc1373d3', 'domain-default-profile', 1, 'string', True, None, None, ()),
    ('change-shape-consumer:196', 196, 'Jaathoom', '157.1', (('^.creature', 1),), (('!.Change Shape', 26),), 'e83fab2d001788c8e958d7dcfe4950448269008e0a0670aca621a532086e39a4', 'ba2ed437f0e9f7f62c3f97971d89f5b1059dd34bda4545c1fed0e60d384b3a81', 'b0b0b0c157365e8de6edad3ba15e6d811da331565e771f2833e49f1036e11132', 'b0b0b0c157365e8de6edad3ba15e6d811da331565e771f2833e49f1036e11132', '0dfa756437fd2ad88c0c006bbbfd1b13fc88febbc8309e12c03e94d63801e2c2', '7938c6e9d28b7780069366ed4794baaf32cdb42cec8dabbf6fb0b498081aba1b', 'de8b87565e1a9a00a12e9addcaef0d0cee7225bb31c847c414311948c214b92b', '079e713c75f96b51517eb78da239f8add8ef6fca4f7886a042f22d4b8465c32b', 'domain-default-profile', 1, 'string', True, None, None, ()),
    ('change-shape-consumer:198', 198, 'Faydhaan', '158.3', (('^.creature', 1),), (('!.Change Shape', 25),), 'daa1584adc98f95d9580482112ebaef545b88906088466edb182e819d0b97cab', 'abefa92c60ed4a281de55d7fcff808d6e3c9fd600d90b7dd73b3ed938a2d59e2', 'df5ea8cf816657c5df4e2e2ed78e77f95ba3c400b8dca02ec1fa40deee1999bb', 'df5ea8cf816657c5df4e2e2ed78e77f95ba3c400b8dca02ec1fa40deee1999bb', '5d53c3de6d6c3a4b8553544a772814374c6a441d9a848df857d7ad27022627f3', '915ecd906c2bde1a76189d69671723df8410eaee292450f2137972ecc0320acf', '75fa3f7133342f5541d3332ff8fce4845e9b4cbc998243fcc16a3c098a91828f', 'd2f63a7df34664570d8d7e4257df024b8cf7d39f93cf2b11c2a566fd3cc8a121', 'domain-default-profile', 1, 'string', True, None, None, ()),
    ('change-shape-consumer:199', 199, 'Ifrit', '159.1', (('^.creature', 1),), (('!.Change Shape', 26),), '9bea116e1e06aa289ea14e4d9063219cd14f4743653e2fdf2c4a9775e4035f52', '44d76f71b0283c074595f862ace06dc3a76007c041cf6365423e4ede085263c5', 'bd8dacb2a4c10eeac4dd685e32eeeb54bcacfdc96e0db53d26375c9d698bcfd1', 'bd8dacb2a4c10eeac4dd685e32eeeb54bcacfdc96e0db53d26375c9d698bcfd1', '7dd5998bf3932b933ba5c05b1883c0591080456e8cda4ff9fcdf7b1409cbf365', 'c62430b8011089e47d2592370efceae4e1e8c5646ae57cce6e4e9fde69265054', 'cfd916801bb636b47809b3e5281dd1a4fbc3735791ae65689a7804cfaf03a0a5', '9e5324cfb455dfabbc82fd7f45b3b7942fdd76ad6cb7eb614ddb8373ee67e287', 'domain-default-profile', 1, 'string', True, None, None, ()),
    ('change-shape-consumer:211', 211, 'Gimmerling', '170.1', (('Gimmerling', 1), ('Gimmerling', 0), ('^.creature', 3)), (('!.Change Shape', 26),), '0642191655dea9fe009d3dbe2dc1b2ef677f012b2d61808fc51e2f1ed127731a', '0655623f00e6dab023f50b311acde20367772dcde91252dfe29f5321ee978583', 'a80c7743bac167a2dde1ba8234320400d4a91d1da6a243bcf315aff64068ef58', 'a80c7743bac167a2dde1ba8234320400d4a91d1da6a243bcf315aff64068ef58', 'eb82c2f7c071130b1d808dbce6688fc488e76923ad020a73149d66d076ce014a', '829f3b686a56a7b9a47ac8859b8d44876e9805673e9123d870458c573162a71f', 'c88cad55c6f227cb75b4cb1591fd359bf6edde751a4136b39e9a530865e767cc', '59df9762662f9afe9b59f0ce39f0857267387480f571e511636b65f5ee69b98e', 'bespoke-overlay', 1, 'string', True, None, None, ()),
    ('change-shape-consumer:234', 234, 'Sweet Hag', '189.1', (('^.creature', 1),), (('!.Change Shape', 24),), '945c078e57de33ecea8769d1db06e66ace4f55905df41b6dcec7d77435c3ceab', 'b9acd365dbefbb075f34bd1c12c7ca97f2f5e46a99f582dc08106128e58cfe31', '287468c3da4ecd50a01f971fff7b65f3579e778a2fc5a9138d047b182ad0ad60', '287468c3da4ecd50a01f971fff7b65f3579e778a2fc5a9138d047b182ad0ad60', '40f8516a59dff9af4324dfc95f60485d5d7b17c59f4cbfbc93e59265c97d9639', '49111473ebeb65af2823e67654ce44e9718ea86562406f719d73a44462765993', 'beea157c471f407f38f90367371db7c518b32db7d7e7ab44dd6af04c4a259963', '5c7787e3474350b5f31478c269ad10a26f5554e4b69a01301530cbff7d5a9f12', 'domain-default-profile', 1, 'string', True, None, None, ()),
    ('change-shape-consumer:235', 235, 'Iron Hag', '190.1', (('^.creature', 2),), (('!.Change Shape', 23),), '2f2ee4f3fd12826c4ac3e570bde5bce8fc1a4c4930cef42cff8480ef9daf63b2', '33f41ba348077bdf72c04cb65ab55e08a6aa01d97d89fdfec3b5a22a0db72973', '2a044fd0c97fabd86f8c43e9d207098a0e45146549665732302ef94f9162fd7d', '2a044fd0c97fabd86f8c43e9d207098a0e45146549665732302ef94f9162fd7d', '6e12c296ab75db1134a60a39219182312e5fe439d0266ca854175c5e513954cc', '14c658f7dfb6f8f94887f1f80de01d96f3c2d1f13df05f9fdcda4e77465f83a2', '76ef96388e36fbec851f9824f6f0029a29a8700be2585d9f805649079a5f6aad', 'fb42ef2ab2177bcfb6a33ae55cf5cbe55fb89998c4f0b9211e45deffc9f7354b', 'domain-default-profile', 1, 'string', True, None, None, ()),
    ('change-shape-consumer:236', 236, 'Cuckoo Hag', '191.1', (('^.creature', 2),), (('!.Change Shape', 26),), 'cd9349fe391fcae1a81c5ff350b10bdc9c93906dd709616d4afcdae7b2df1171', '40bce2ff671efd04464e7e66b0d1a03cc4ab108d360c029f0187b6ab180cbc3f', '2bca457118a79657e5d4aca924596a05298323959bd9cea98306a2480bd8f1ea', '2bca457118a79657e5d4aca924596a05298323959bd9cea98306a2480bd8f1ea', '84098f8ca1a7128f4c059aff4e637b13b435564c216f402e426cb412e3b9e76e', 'c8783107e89bd0c05e42207450faeb037e49beebe3b596baf44818cebdc9204a', '435546b0ebe15d4f8d7a505b3c0274af0e046200c36b83041b3bf1a2c60d32e3', 'b7e0bf8785fef3feceec97ed6661a9176338460cdd2a3628ebe5bad7a279271b', 'domain-default-profile', 1, 'string', True, None, None, ()),
    ('change-shape-consumer:260', 260, 'Imp', '206.1', (('Imp', 1), ('Imp', 0), ('^.creature', 0)), (('!.Change Shape', 23),), '0222d55840e76ab94bf6daf5f5007a52711687640b32c02c4457c2ac02972a52', 'a924d24c59613a7ca3c093455e90d6e297c852b7fc389177770416620d4e6ced', '872c5409eaff05c45c6cd1fa5a5bff0eb1a94fa99c77f9c730f3b72bc1f6c604', '872c5409eaff05c45c6cd1fa5a5bff0eb1a94fa99c77f9c730f3b72bc1f6c604', '349660f24950d6324a4ac5d2a9965e478feb749616d826356710cb9e805a5a26', '715adc4a7f1cf5e5111f937173f7a64f082525cee9c4d2cb0edc70a117407f75', '42f6b10f613abd1b86322ca4161d9e672cbe9c5d23d35288468b8045bb71b319', 'fee6843db385d2d5c469439a67ad76fea617f281358a72701608afc138d47715', 'domain-default-profile', 1, 'string', False, None, None, ()),
    ('change-shape-consumer:271', 271, 'Lamia Matriarch', '215.1', (('^.creature', 1),), (('!.Change Shape', 25),), '6bbc1c389268eb56c9e76addd46b31fb6b6a266e8a0c5d2c5b43054b7bbbda9a', '7008c4729505f8a1ed5df6c8f3488f77feb86fa9ae21cf0bc230c4692fde1f0d', '25e098c73129e8486d3effea3b30b9518011c646cf40b939dd5fed75f8dfdf9e', '25e098c73129e8486d3effea3b30b9518011c646cf40b939dd5fed75f8dfdf9e', '195fd7c3dc83745e8acd629d12dbe2cfa21238b22f0e158decb3a816185a96ae', '83d104cc2cae5e88d727f79ceac73871ec0bff87f4408e2857b7c3026c8d50da', 'ae7e757bf4cb3d5585b0d2fa5a0dd26cb093099bc3ea63cf6f55613498918d1b', 'f9468618aaa4469e5f25eb2eaf0798bd4a0e90960d707f92e8c32a3efe5412e7', 'bespoke-overlay', 1, 'string', True, None, None, ()),
    ('change-shape-consumer:272', 272, 'Leaf Leshy', '216.2', (('^.creature', 1),), (('!.Change Shape', 25),), 'faccc74f7373081d86fbd37afd6ab7788ee2590164c4483d206a4af0171cd3eb', '30986d60360d11b843c052de51f510d834972640bc21fe39279ab60e285c736c', 'cb9d585760f4998da18d38170ab8a1bcc21cd628aceeeed8dfbe0cbcf34e3b93', 'cb9d585760f4998da18d38170ab8a1bcc21cd628aceeeed8dfbe0cbcf34e3b93', '520ca5dd15221cb3e03644690b67d342a4f122875d9ff57039723a98fbeec0c1', '581d69d35c48eb97feebb0ad10adf7277d40161bc77b0081549a90f3d0bd5d0f', '9c890896aed1897d68e36c7792658703c90b55b8a1408bd1a34ed9fa93b6dda9', '0596789a035fda7ba289172c2ab5374bba1c26a7cbd625aadc3b8c4c0488651d', 'alias-producer', 1, 'string', True, None, None, ('one-with-plants',)),
    ('change-shape-consumer:273', 273, 'Gourd Leshy', '216.4', (('^.creature', 1),), (('!.Change Shape', 24),), '774a4ce1dca83d43c65dc641f14cd6fdca68a01efc60f07866957db9fcebb362', 'c305a0db7ca89a41dfa949f13d03be23d9383fc3cb3f2a747c5dfd76a90abfc7', '6a4b72e469cd7d5ef5843dee8f7fdaed7bcd7e3fcaef6f39d2486932a87443aa', '6a4b72e469cd7d5ef5843dee8f7fdaed7bcd7e3fcaef6f39d2486932a87443aa', 'edd082a0e2c9bd73a3219a0fb9a883e88d99a5101931430cc1bd152d6d39a8bc', '7e63b5aa627943bb7fd8ddd03f4908135d18252f1ce734aeee8ca096a4deac78', 'd61cbaef7363a8759d627b5d8fe947dd2856f680fcfffbbd967f4868db77d97c', '1eb4a5296c36d36cf3bc22c579610908db13df5852d97130e95febe58cafae6f', 'alias', 1, 'string', True, None, ('base-plus-form-override', 'Leaf Leshy'), ()),
    ('change-shape-consumer:274', 274, 'Fungus Leshy', '217.2', (('^.creature', 1),), (('!.Change Shape', 23),), '1f0cbadc165818a87004d1c868a210d1f77634ccde3d757a217733cc91febcb4', 'fe900aa65e66e38c85c22e2e6c1dfe8d158398e2aa2b60f939807e1f62639899', 'c429a1f6d36b20fb1c084346ba9c462734c5aaab747f148ba9a251b840abd82a', 'c429a1f6d36b20fb1c084346ba9c462734c5aaab747f148ba9a251b840abd82a', '83a853ab4e9c870dbebca55f03a1fb0fff53409690c8323df556301a9c67b06d', '2250d42b3bebbf8985ad62cf07a0e711f4b8e721dd742a8abf7f7a443ec209b4', 'bec608522fd59b084042bf9ef9c1a0c10c4e0fb41ece7c7ffd9d93e83f084710', 'a183dbe683abcbe0b03319dca736d73f5d381e3ecaefc8123c52720a4155da61', 'alias', 1, 'string', True, None, ('base-plus-form-override', 'Leaf Leshy'), ()),
    ('change-shape-consumer:306', 306, 'Naiad Queen', '246.2', (('^.creature', 2),), (('!.Change Shape', 29),), '16bf8ec1074aa2de47d7711ef3136ff641f1d30fc43dcaaa15d74a04e9d3f608', 'ba413a239dd37969c968a8c56c0ca1d97658354cc0b4ffdf45ee87c0bcae07ed', '4499b4be6799960bdf8237f139c682d47c15860d386b86a4397c77a461fe3502', '4499b4be6799960bdf8237f139c682d47c15860d386b86a4397c77a461fe3502', '97129c650a4712dd9d9465a1b231ff90ae656cf01848b1868cffb5f24ec3738c', '8d17e45823300d6f3b6223d24798f88bf3c8bd858489f6ca6f686de893efba96', 'd95d4d91fcb635695f39b90eb219a3df5a275811f88793c1dc35ddc1c4b364cd', '80ea5fec0c60ee479038c0e1452496a04e1478d14f2b741a2c350523df18e4b4', 'shared-producer-consumer', 1, 'string', True, None, ('enclosing-shared-producer', 'Nymph Queen'), ()),
    ('change-shape-consumer:307', 307, 'Dryad Queen', '247.2', (('^.creature', 1),), (('!.Change Shape', 27),), '0b1946f3e1cafa3b0eee04475e9f8dbc5794ac43ce4aa6bac82e6654ed15a590', 'e6331d31abcc4fc13af363d6aa57bf5022b0e5ad0ebb523823b9411d47bd65fa', 'fd079875523adf71aab9d4000be7f265ba8087a1e4950a9745cb74e771a05cb7', 'fd079875523adf71aab9d4000be7f265ba8087a1e4950a9745cb74e771a05cb7', 'd93a1c8a6eee78fb1b8e5f587aea751522ae37a114014152d145f7e1ef506f4e', '8f0d713a4d08bef80b1fc3a2c60ef20f264cbb79867292148680d53fea8d4612', 'b3cce877f5aefb419f64349c89017e971c64229328d3938bf50dc52877f0f9d2', '80ea5fec0c60ee479038c0e1452496a04e1478d14f2b741a2c350523df18e4b4', 'shared-producer-consumer', 1, 'string', True, None, ('enclosing-shared-producer', 'Nymph Queen'), ()),
    ('change-shape-consumer:314', 314, 'Mountain Oni', '252.2', (('^.creature', 1),), (('!.Change Shape', 25),), 'da9816d596ea7282ed37b42d1a8dbe45a9b458f934df4ba4f60611e223b8dd94', '3e33b727188394ed26b43f5312bdef632b4a17acd2dce6a34972d6b0dd31d521', '63affa8c437e5155107272eb610c5e43aa3b743569bca644bc87e44997c31e29', '63affa8c437e5155107272eb610c5e43aa3b743569bca644bc87e44997c31e29', '5675f8e2a4e2d36001b4c105518f70994b89dec5330332fd0a887125fd4cf529', 'ab44ab6b788bd6e0bee17abc2bd97d31de76506fc3b69e4968506ed43e8c63aa', '1aa061bd417c0435003e74f47981290d6d2ad967d101bd093d6551e93c823997', '01d35457ff27e5286be16f7da772e12c10286a8c49e8b8691d4abd4bcd805c5d', 'alias-producer', 1, 'string', True, None, None, ()),
    ('change-shape-consumer:315', 315, 'Snow Oni', '253.1', (('^.creature', 2),), (('!.Change Shape', 28),), 'bab8b4341612e55b069452349d1c6462c525afbff691614f32db988184f32444', '8344e01d7222e58f0e97b39e115bfbb114e21247b73aa718fa068fc85ecd2f8e', 'f836dcd3196a0fe46c38512f03b2ed31f48478232e8b3bec2e5388d596d683ed', 'f836dcd3196a0fe46c38512f03b2ed31f48478232e8b3bec2e5388d596d683ed', '2cfe97a0fedb3685275daa27c85adacc9865c783912889ff0e88c5293f6e5831', '9189e8a785ad09889256c67e7d6fceb738f63b07215456de5e7caa217b3d38d4', '55ee9084c7065838907e329dfd355cc6966519454c39175316c0bcce9d45b888', 'ecc53997c52abda694c697293c5a9d8996a1daaa00eca6a3529250063edb7146', 'alias', 1, 'string', False, None, ('exact-alias', 'Mountain Oni'), ()),
    ('change-shape-consumer:316', 316, 'Caldera Oni', '254.1', (('^.creature', 1),), (('!.Change Shape', 27),), '6fc15b861a27b04e609cde6a23975dbf0dbb0731b18748466a09bec3c868c08a', '8344e01d7222e58f0e97b39e115bfbb114e21247b73aa718fa068fc85ecd2f8e', 'f836dcd3196a0fe46c38512f03b2ed31f48478232e8b3bec2e5388d596d683ed', 'f836dcd3196a0fe46c38512f03b2ed31f48478232e8b3bec2e5388d596d683ed', 'e31c1b17664eb65e0aa99aa8738a4b54395874e82c27c713d74fe88d254fa5c1', '9189e8a785ad09889256c67e7d6fceb738f63b07215456de5e7caa217b3d38d4', '55ee9084c7065838907e329dfd355cc6966519454c39175316c0bcce9d45b888', 'ecc53997c52abda694c697293c5a9d8996a1daaa00eca6a3529250063edb7146', 'alias', 1, 'string', False, None, ('exact-alias', 'Mountain Oni'), ()),
    ('change-shape-consumer:317', 317, 'Island Oni', '254.3', (('^.creature', 2),), (('!.Change Shape', 29),), '4265b04ec5af63995a3486494e6f6923b16f56031cdb3931717283b1c6723eeb', '8344e01d7222e58f0e97b39e115bfbb114e21247b73aa718fa068fc85ecd2f8e', 'f836dcd3196a0fe46c38512f03b2ed31f48478232e8b3bec2e5388d596d683ed', 'f836dcd3196a0fe46c38512f03b2ed31f48478232e8b3bec2e5388d596d683ed', '9de45daf3a7faeb33e8d76a02bc34317f5982aaef3b6c03f70e4c722e447aee3', '9189e8a785ad09889256c67e7d6fceb738f63b07215456de5e7caa217b3d38d4', '55ee9084c7065838907e329dfd355cc6966519454c39175316c0bcce9d45b888', 'ecc53997c52abda694c697293c5a9d8996a1daaa00eca6a3529250063edb7146', 'alias', 1, 'string', False, None, ('exact-alias', 'Mountain Oni'), ()),
    ('change-shape-consumer:337', 337, 'Voidworm', '270.4', (('^.creature', 2),), (('!.Change Shape', 24),), '13b8e015d13c6174ab6122ba9a1a0262b6a2df73a41e0bf4060cd48fdc52a718', '436580241017eaa4ea3125d15b1d462e52ea43454267badadf60d786977133bb', '52aaa0278e05c678b5f008bd56ac6240e22eb02e62e73e105fd9405a831add59', '52aaa0278e05c678b5f008bd56ac6240e22eb02e62e73e105fd9405a831add59', 'c9fcbe78aefea217bb2865528c01b02f4c52a939ac0c9591a9352c501d969acd', '4c5adce6703d8bb7c0f0bf96cc264883654e01dc585c0d81025f740a86fe27a0', '22c39069acb1e569a39097263aa13a833afde71c89298a9cf7d6c920b314ecbf', '5785348d55b2357b5c4f4869f12871653f97751139dd28e0b4fd589abdd93996', 'domain-default-profile', 1, 'string', True, None, None, ()),
    ('change-shape-consumer:339', 339, 'Keketar', '272.1', (('^.creature', 2),), (('!.Change Shape', 26),), '3188c51dd4a4679c2c4b4e4189a5136a31ff3364d91c053c18b4855aba099bf8', 'f4cb949b3cd9cf92a6d9c0e2e6836fa7ea4aa4fcbfcc93090ca387f7bfdf5348', '84f561a29675dc57b808237c15fef6d71735204edc76366a2d5fcc675c447648', '84f561a29675dc57b808237c15fef6d71735204edc76366a2d5fcc675c447648', 'acdbf59531512fd250839d656a40b8d833ce0b37ce042c8e75ea17f9d39b18d9', '145d68ab65b70b84ca437a15ae449cd34cf69384545643a62edf2294c9c28485', '582508263bda06d73f32e5e801c504b245130696230f0219e643a5cd19f117ad', 'fab31234073bba57d8e304eb1e77c20748d098699afb3d9679799e0eaab560c3', 'domain-default-profile', 1, 'string', True, None, None, ()),
    ('change-shape-consumer:340', 340, 'Nosoi', '274.3', (('^.creature', 1),), (('!.Change Shape', 23),), '5c36f9036ce8466e2bbd35c29d80662c80c67e4f0a551dfe5a46fbb898f57daf', '0a952740078392bc7cb760db25024db514eea3505c99d0aefd647f2d43460710', '01ba0006d28aaca35a5e16debda6f8b49daefbe29b11ed3fc71a0755ece9945f', '01ba0006d28aaca35a5e16debda6f8b49daefbe29b11ed3fc71a0755ece9945f', '7e04a19b1f8467518572b0ad4f2b30cb86c19135a3e2556e1636cae8dbc9f8ba', '806eb200458c050f64cab1ad647cb226af2efbdea239b8c4cd63d826803c883b', '253b290a1163122c15cfe543d48951be560007e846fbb28d234003f733a2e6e7', '2a6f73ee2fedc0a25af394e913cb1de2b661f709231cb9bccaf1e60389188593', 'domain-default-profile', 1, 'string', True, None, None, ()),
    ('change-shape-consumer:342', 342, 'Morrigna', '276.2', (('^.creature', 1),), (('!.Change Shape', 26),), '80e95930c05e3816d91485f1f68766f38c3546b39f9fcd7d8a3db5d904507b72', 'c0942c2f62de441875f3fe39b3e7553660e2ff0fb886997684f5670d945d123e', '07f05d16654c4aefb3d1b1350a0f157c55e8f47ec95f6317a9b085fd3f639d66', '07f05d16654c4aefb3d1b1350a0f157c55e8f47ec95f6317a9b085fd3f639d66', '491351a70b46b92913e8be0c2289453c13ce760066075a62db996d18a6338765', '949f2152c8bd2a5e00ea1318a86a3e3acfe75f45da683ef093f46e91f37df390', 'eda7af08b322ff0e5969011d32c03a07ef6b799cc8d8b20d1baceba970a6bb3e', '1871efcdfdb9e9b307f94fd8c1d07b8f9d013501d5827268b81e1b9453008b28', 'bespoke-overlay', 1, 'string', True, None, None, ()),
    ('change-shape-consumer:346', 346, 'Pukwudgie', '279.1', (('Pukwudgie', 1), ('Pukwudgie', 0), ('^.creature', 5)), (('!.Change Shape', 26),), '057a6b2632ec989e6150b4e8769b5422cb3b5e5c2835053fe9a8e0c7f710a70f', '45840b21f0b078596b0ab9613226481355ef3c2e90bcac7078d88e645c2ddd6e', '25dd7dc83a4152c623881f2a78e8fd16e91d31a00e4b7b2329ca2938dc5a51e6', '25dd7dc83a4152c623881f2a78e8fd16e91d31a00e4b7b2329ca2938dc5a51e6', '02af021b763a026a47ee03b23182bc587f3c463bd148a660bc7dc19ac5065f55', '3e6be644421cdd853dceaa01a976922949ba23bc6f2ad48bfedacdf543b14787', 'fb56e6f1df6ed897525d6dc5024748681a531437586a5ad2b5534128b28e7cf8', 'ea163339b9299c64221f1dd8b1e5bf9253beaab5c1bc7a6531cf43292273865c', 'bespoke-overlay', 2, 'string', True, None, None, ()),
    ('change-shape-consumer:353', 353, 'Raktavarna', '286.2', (('^.creature', 1),), (('!.Change Shape', 24),), 'b0474a952b58d43c467c4af621706a5b2e893fe4d17b19048bafb8a0e29c6db9', 'a35f44f5bf0f9e128369e4ae640c65857991f110ed55a978aebb2aa5f781d5d9', '52bf3dc92cd2f56d33de19f8b831b926c3405dfebb83e09efa5c4a75e7df26a4', '52bf3dc92cd2f56d33de19f8b831b926c3405dfebb83e09efa5c4a75e7df26a4', '0a04b1f66d3f361cc2fe7369c9b9c1000f102d73010f478ccd726deadfa6dd1f', '62c912aa17c0782056cbeca32ca436adbd764f9ef6f654ff66d81fadf9ffacdc', 'cf2b34b00f44ae3eb0f6d784a41bb4e8dbe15a0106034daa99bed43a10d3dd0e', 'a063eb025f1e9d96e9bf326ecc95c7896464fda6613de276f808bb4706bc4377', 'bespoke-overlay', 1, 'string', True, None, None, ()),
    ('change-shape-consumer:354', 354, 'Raja-Krodha', '287.1', (('^.creature', 2),), (('!.Change Shape', 26),), 'f203d1b496cb14c5f47138afd19d3881448f44703f18d8a1d1bf2588bae803b0', 'c505512b0683c103a072011572b34907be2147fad5e279c559693497b5a15265', 'aeec286851f20716aaf621ef607d85efb6db931d3ce50f6fd0ac47d00e608f36', 'aeec286851f20716aaf621ef607d85efb6db931d3ce50f6fd0ac47d00e608f36', '9840925902857ff7642fa806c3d166c7eb4e6b1607d89a25d09536e5bdb890c6', 'c61507379db035c46cf9a92355c277bd558fe7eb0535c7c2055ca3395048f7bf', '08cf8b56ebd535b5d6ba2959a026814c0a604c254117e0d6bcb8185a6d79ae2a', '6602f2e28677076d93b84643c2ffbdba6010a0378ba68cc13ad5cce8aadce8b8', 'domain-default-profile', 1, 'string', True, None, None, ()),
    ('change-shape-consumer:418', 418, 'Vampire Count', '336.3', (('^.creature', 1),), (('!.Change Shape', 27),), '79ddfe3186332f62dc092d9d27a4ad77ed6b8528fe8af208cac81f8cb8f3f6c8', 'a25ed71b786ac07baae1c547cf44bf375599fe4672cf41474b03dbcce9faed02', '8d20924dd7aac369a4bea9cd49da8fce055cce6460ba8b6a619871772a0323dc', '8d20924dd7aac369a4bea9cd49da8fce055cce6460ba8b6a619871772a0323dc', 'b754ceafaa25873343e2cdabe13391bfc1c4aa1eddb03c53cdeb03bf53623565', '00ad2dff75cb8e212e6a879c993e90eaaf42000b6405d4a4539252b9f1512832', '0bacdbbe8244543d4d2cc08c7b3ccdd188650db0fc8180af587142a332dfe9a1', '54ff9e0310f7bad619691e558ecb48f90eb1793522f8d9e3a59e13868e676967', 'explicit-form-profiles', 1, 'string', True, None, None, ()),
    ('change-shape-consumer:419', 419, 'Vampire Mastermind', '337.1', (('^.creature', 1),), (('!.Change Shape', 28),), 'be3ac563c046450cb0039084d18b50d95ea38cbfd1b839f0ab98644f08dc423a', 'a075841b39cb0f53926436eb6e48edef6701c36856c2efa24d2b43776ba908ec', '4fba73b00ad1127c0c435f492a27354f1be6e1c91c387546e913d8a29047a67e', '4fba73b00ad1127c0c435f492a27354f1be6e1c91c387546e913d8a29047a67e', '7e5939b64956549acf6b14e5f296220238b7cb9390c738b5a3168f7a5962f198', 'a038f4febe53e5298b55d4dd10499ef8243ef2274282f3922451ec1696f384d3', '05e627eae8244662866b5c241a8e7847fd5d72c3e1930dd92cdb367e1f4717b3', '41834fd9a211912da9405a0037624f180e3778b051bfefaaacf8570e851976f0', 'explicit-form-profiles', 1, 'string', True, None, None, ()),
    ('change-shape-consumer:422', 422, 'Vilderavn', '340.1', (('Vilderavn', 1), ('Vilderavn', 0), ('^.creature', 1)), (('!.Change Shape', 26),), 'eacec6a7f34bc6543e6ecc97dfa7dc6092881d3097f6d838230e6ea44582edfa', '1f7442555b0ee6e6e220064f3035988333a037099b1e4a2f9e471e765b68b8be', 'aa849584b36ca8dd1bd378d0e7da955c1fd14fb99eb9dead9f2b2d05971230f1', 'aa849584b36ca8dd1bd378d0e7da955c1fd14fb99eb9dead9f2b2d05971230f1', '64ca9d2da7984f56489aa95013792811584ad2c5e8eea4b03443dadc4ffd6aff', '5debe4fbefee05a2898d6ace2329fa95755371ece4cd5d38c8e5223e373ac486', 'ef8d2f160bf3a3f524b68a5a2cb5c97dc90799545d14508fcaf6aa42e46dd116', 'b869b1047defbbd4dc71c984ae9ec76d8d2146c4d9b752a708f1ad14dc120dac', 'bespoke-overlay', 1, 'string', True, None, None, ()),
    ('change-shape-consumer:428', 428, 'Wererat', '345.1', (('^.creature', 1),), (('!.Change Shape', 25),), 'a0646c82ea55c4756c36a6b3c37bec823d2261015a3e3bc364b7f71a6615e6f0', '44c49256b3b832e0352f006484f6dc4ae92f3e5113dd4371414e8b4e566827a1', 'e6ae2b0095dd13d526dbf4e5f6fc320dba5a627933f38a72c250ea6dd8077ef0', 'e6ae2b0095dd13d526dbf4e5f6fc320dba5a627933f38a72c250ea6dd8077ef0', 'b5addd6310e265385b4c6e3c25e30ee74dedba7ebbfa783f07a246372646011e', 'ee96ed76491062f3c4e551bb5937ca30bb832350b9c77e9db3f283a95d282cc1', '7f6716332e5af9c8df7aabc3f13d76a86efe333942457d824aba0b97c7a1c334', '201d2fdddae296a0f18d89e232ed351659c7b50a87138c11fb1aa203d9ee85cf', 'explicit-form-profiles', 1, 'string', True, None, None, ()),
    ('change-shape-consumer:429', 429, 'Werewolf', '346.1', (('^.creature', 2),), (('!.Change Shape', 25),), '292bf3fa0f9df55b269d31681a6ec905d6a5b0accba9cb505044060b00e7cb98', 'c341fddabf96859e89a6a2a380a2d15aa9ca92b227190b604177d52ccf3faaae', 'ab86f7d72c71cfc189678b69a79f0b8ec95344ceaa5c85ec9f557cf21fdc3ee2', 'ab86f7d72c71cfc189678b69a79f0b8ec95344ceaa5c85ec9f557cf21fdc3ee2', 'b226f4f23eb9ada2470e330b3d5c0946cb7ff92905cd98f264ffc90d65f3d8ee', '59d5634ed7d5f874efc8bdb19d7cfd6f4c561c6b01a4ce6a65f99786076be80e', '59d19ef3b75b3ec20205f7eed3d5289ffd0a5d885b20440b1dab114892eeb146', 'e74c6794ec5d4b6440362bb0bdd1be791a7eb2746544429b534585ffcfd96962', 'explicit-form-profiles', 1, 'string', True, None, None, ('knockdown',)),
    ('change-shape-consumer:430', 430, 'Werebear', '346.3', (('^.creature', 1),), (('!.Change Shape', 25),), 'c7f416e09064b2cad3c527015151f8d8a861091a9d025604d656493a2c354523', '19e5a6a67dd6d4989efd9e9ede7dba42e13107bb34bcfe1e74c27f2e641fe04e', '9cd5f91875ca11ad9ed41334e7dce0cedb4858c4c6811082bad5a36c3efe622e', '9cd5f91875ca11ad9ed41334e7dce0cedb4858c4c6811082bad5a36c3efe622e', 'ca676dd483108abbff1c647725f953e533f80f270199aa80acfa5a5fa7923a09', 'fbc0623f3dfaac369f915d2efb5dbb900b8dbfb386a44151505c6f750f968ce6', 'a576cefcc0d5bc0bb9d52671c391b12c76df6c481c83c60b401ed7624f034448', '2961a7fede588bef2c43f393ae1be2a195038f6201fe544d600ae2f9eabb45e3', 'explicit-form-profiles', 1, 'string', True, None, None, ()),
    ('change-shape-consumer:431', 431, 'Weretiger', '347.1', (('^.creature', 1),), (('!.Change Shape', 23),), 'd32817690a67b09d3e5d4d1f96a88e778f2c87a2061631a6128f393374059b4f', '3227eeddb203f022d64854fbc0a6141adb8934896abb4334bdc2f60dd8ec06f5', '4c5de36c3443454d99b2e8eb0e37e13f36c370998dd8c4bb20f5a3b72589bfac', '4c5de36c3443454d99b2e8eb0e37e13f36c370998dd8c4bb20f5a3b72589bfac', '83e287467f8206d2197a6a2a7dee02ea9c302297bffd95378afe098795cb7dd7', '4bfd9bfccc8acc43662122de8b4e257b0abedb0ae9a23b27d7604ec919e04158', 'a1da02dff9890d1f7da0f85719886b3b4d7a76c04ea64781b979a9ba3c94d31b', 'c485bf516fe828d38db72e0d1f9a6941c7fa17571b221371217a62aafa385b4e', 'explicit-form-profiles', 1, 'string', True, None, None, ('wrestle',)),
)


# Provider spec fields: rule id, source, locator, carrier path, selection path,
# current block/member/value/selection hashes, reviewed purpose.
_ProviderSpec = tuple[object, ...]
_PROVIDER_SPECS: tuple[_ProviderSpec, ...] = (
    ('change-shape-glossary', 'core-mc1', '358.2', (), (('^.ability', 7),), '2b112ab4886ed04c44004a3cbf876404265d7488c35fae66c9f9369accfc13ef', '3e7031a4e6375e320ba289f16aafa29c717dd609dc45067796a6ddec84a45b13', '7b21a5a72b2799d3a674f879a9862c216f5ed0acbeb4957b0a48c484b70681bc', '7b21a5a72b2799d3a674f879a9862c216f5ed0acbeb4957b0a48c484b70681bc', 'Monster Core Change Shape default profile and disguise rules'),
    ('polymorph-trait', 'core-pc1', '297.2', (('~.aside', 11), ('Other Spell Traits', 1)), (('Polymorph', 5),), 'b422dfae557547804e8fe08b84061944c622978c2eab2f3cd8f12645ba071ae3', '7f34843e469eff7269a0e53a08e35700b0fc624691d239e4860eb734ab419676', 'ea71d37deac937771f437051109d2f45787fc6c075f3901ff7ad4e399c907180', 'ea71d37deac937771f437051109d2f45787fc6c075f3901ff7ad4e399c907180', 'polymorph exclusivity, counteract gate, magical granted Strikes, battle-form restrictions, and size-fit disruption'),
    ('counteracting', 'core-pc1', '303.3', (), (), '65d0a1286316498496d662fee3ba10754f64738831a02a9d45627057e717ea49', None, '65d0a1286316498496d662fee3ba10754f64738831a02a9d45627057e717ea49', '65d0a1286316498496d662fee3ba10754f64738831a02a9d45627057e717ea49', 'general counteract resolution for competing polymorphs'),
    ('impersonate', 'core-pc1', '238.1', (), (), 'e20d86345c66d418458e458e0a8035a29c3a29231a757311d3d4bf19dc333840', None, 'e20d86345c66d418458e458e0a8035a29c3a29231a757311d3d4bf19dc333840', 'e20d86345c66d418458e458e0a8035a29c3a29231a757311d3d4bf19dc333840', 'generic-individual disguise and observer adjudication'),
    ('size-space-reach', 'core-pc1', '421.8', (), (), '57f6c8bd51c2367bedfda5464ec295229a54363d5576a671fbda1fda3ab01fb6', None, '57f6c8bd51c2367bedfda5464ec295229a54363d5576a671fbda1fda3ab01fb6', '57f6c8bd51c2367bedfda5464ec295229a54363d5576a671fbda1fda3ab01fb6', 'transactional changed-form footprint and reach'),
    ('one-with-plants', 'core-pc1', '347.3', (), (), '8e92027657fd97fe7493ce4d425a23de9ae34df06984a3f397fcfcc945eb3f72', None, '8e92027657fd97fe7493ce4d425a23de9ae34df06984a3f397fcfcc945eb3f72', '8e92027657fd97fe7493ce4d425a23de9ae34df06984a3f397fcfcc945eb3f72', 'Leaf Leshy plant-form producer'),
    ('dismiss-action', 'core-pc1', '419.3', (), (), '81e502fc464a53086e254827e9617bee6c7f98dc07ab5feb2ffe8d0bc037050f', None, '81e502fc464a53086e254827e9617bee6c7f98dc07ab5feb2ffe8d0bc037050f', '81e502fc464a53086e254827e9617bee6c7f98dc07ab5feb2ffe8d0bc037050f', 'Mimic Form dismissal contract'),
    ('knockdown', 'core-mc1', '358.2', (), (('^.ability', 20),), '2b112ab4886ed04c44004a3cbf876404265d7488c35fae66c9f9369accfc13ef', 'e73d25e1cc45a161fb872af09780aeb1cb4c5803e734773b4a9720d3efd17949', '8e17d50151eae8b5884082222660d2e965bca7f935df17775d5b907b34870ced', '8e17d50151eae8b5884082222660d2e965bca7f935df17775d5b907b34870ced', 'Werewolf wolf-form jaws rider through shared Strike'),
    ('wrestle', 'core-mc1', '51.2', (('^.creature', 1),), (('!.Wrestle', 22),), 'aa839ac7cfd65971c030ab675825713d9704054c399345fc6f8f3a7489d50c2b', '00d494a34d90dcadbdacf1afbeab3cf63ec517575210ae24952e82b399e5e211', 'b288cc12f095e95a7614f60fec861d4eb0242c3c95ea5609122f978b306ccf07', 'b288cc12f095e95a7614f60fec861d4eb0242c3c95ea5609122f978b306ccf07', 'Weretiger tiger-form ability producer'),
    ('form-producer:nymph-queen', 'core-mc1', '245.4', (), (('^.action', 4),), '27989f98135b154fbe2ef8714fbe92d6021191e38f49e1e51b6d132eaa74d277', '7e32784391609da47379263090c6cdcd9a17afe293b5cbef0b90e74e83e81062', '4bd9bb88b749ba4531d116237e79d78ba0b7077f8521f21533d173bbd951339b', '4bd9bb88b749ba4531d116237e79d78ba0b7077f8521f21533d173bbd951339b', 'shared Nymph Queen Change Shape form producer'),
    ('form-producer:leaf-leshy', 'core-mc1', '216.2', (('^.creature', 1),), (('!.Change Shape', 25),), 'faccc74f7373081d86fbd37afd6ab7788ee2590164c4483d206a4af0171cd3eb', '30986d60360d11b843c052de51f510d834972640bc21fe39279ab60e285c736c', 'cb9d585760f4998da18d38170ab8a1bcc21cd628aceeeed8dfbe0cbcf34e3b93', 'cb9d585760f4998da18d38170ab8a1bcc21cd628aceeeed8dfbe0cbcf34e3b93', 'local Leaf Leshy Change Shape form producer'),
    ('form-producer:mountain-oni', 'core-mc1', '252.2', (('^.creature', 1),), (('!.Change Shape', 25),), 'da9816d596ea7282ed37b42d1a8dbe45a9b458f934df4ba4f60611e223b8dd94', '3e33b727188394ed26b43f5312bdef632b4a17acd2dce6a34972d6b0dd31d521', '63affa8c437e5155107272eb610c5e43aa3b743569bca644bc87e44997c31e29', '63affa8c437e5155107272eb610c5e43aa3b743569bca644bc87e44997c31e29', 'local Mountain Oni Change Shape form producer'),
)


# Related spec fields: rule id, creature, label, locator, carrier path,
# selection path, current hashes, scalar path relative to ability, current
# scalar hash, legacy member/value/scalar hashes, classification,
# relationship, provider rule IDs (glossary is added for derivatives).
_RelatedSpec = tuple[object, ...]
_RELATED_SPECS: tuple[_RelatedSpec, ...] = (
    ('related-change-shape:azuretzi', 'Azuretzi', 'Mimic Form', '271.1', (('^.creature', 2),), (('!.Mimic Form', 26),), '99825cbe3c6860fe09bfa8300c43c84effb0eee5a86e0ba714136bed497d4b4d', '7af8206fde791f8d1cbeddc62a44fc0b6f76a971f76634463b5800b22c14f81c', '37444d922432bf60bcc1a45792277ff6dd8b948fb7852a21a18d321a10c46d30', '37444d922432bf60bcc1a45792277ff6dd8b948fb7852a21a18d321a10c46d30', (('Description', 2),), '044f8a5fe69ba028ba57b72b44347af5874e242e8b861a20b4b538ca5b51b580', 'ffae35864dbaea991f020c2bd14d44452122fb7fb071a5d03d21b841e1c585d8', 'e4f60f723c4cb631ffb2d05625d18b70682e8c6142f4c6771999097b046d3d66', '044f8a5fe69ba028ba57b72b44347af5874e242e8b861a20b4b538ca5b51b580', 'personal-change-shape-derivative', 'derivative', ('polymorph-trait', 'counteracting', 'impersonate', 'size-space-reach', 'dismiss-action')),
    ('related-change-shape:young-conspirator-dragon', 'Young Conspirator Dragon', 'Conjure Disguise', '110.3', (('Young Conspirator Dragon', 1), ('^.creature', 0)), (('!.Conjure Disguise', 24),), 'c1855f403bd95e61192e2c133735f00826fec4692c02c93197fa9efb1d58845e', '9137e30be9bc471651dc4a8789d1cf6a8ceab5534614800c18c18f5aced3462a', '8862e3d3acefcf356c1ab76181c471a0ad20c91c865a02736d35231971d7eb19', '8862e3d3acefcf356c1ab76181c471a0ad20c91c865a02736d35231971d7eb19', (('Description', 1),), '06666a42903791718aa2dfcc97151c0c0e5e0658464f9352a8e21d1ad919f05e', 'cb8cfff40f6fbd947c16d1a0c979c29d6618197d7afa41a6626a53b121daf9db', 'ab1c064070f2491ad0118762e953be5b059ca059b13ed10d8873689309f527fe', '06666a42903791718aa2dfcc97151c0c0e5e0658464f9352a8e21d1ad919f05e', 'nonmagical-disguise-derivative', 'derivative', ('polymorph-trait', 'counteracting', 'impersonate', 'size-space-reach')),
    ('related-change-shape:sea-hag', 'Sea Hag', 'Sea Hag’s Bargain', '188.4', (('^.creature', 2),), (('!.Sea Hag’s Bargain', 25),), '6a56122e83e8291797ca31069ca6119553c1a131cc11b25d4af3e7d67932dea2', 'e9c93f56a9b6ff138ffa9d8ae92bec6b9a91e4736e443454af0f36c2399fe3f7', 'cddb0197f0f52ad085ebd81b202d39acb711cc0fb6e44a1d160031cf4654c778', 'cddb0197f0f52ad085ebd81b202d39acb711cc0fb6e44a1d160031cf4654c778', (('~.p', 1),), 'ed13589ce3de7a6a47783ba03463e8334284fe067fec24e1862f0bc475301839', 'd503124837011b8524160d90b789347cf8608d0aae4da190586e24f87eeb0409', 'c420e4a0bf5c47667c6357cfa75a60e57ab2b5eb9e24cd9ed1a52f3c5ca5a252', 'ed13589ce3de7a6a47783ba03463e8334284fe067fec24e1862f0bc475301839', 'target-transformation-derivative', 'derivative', ('polymorph-trait', 'counteracting', 'impersonate', 'size-space-reach')),
    ('related-change-shape:vilderavn', 'Vilderavn', 'Souleater', '340.1', (('Vilderavn', 1), ('Vilderavn', 0), ('^.creature', 1)), (('!.Souleater', 27),), 'eacec6a7f34bc6543e6ecc97dfa7dc6092881d3097f6d838230e6ea44582edfa', '3a09e2f2f4730fa1a67772e5fb6ac00ffad8e16e46254f28cf3613812b63e5aa', '1b0c82717683cf1beb644c835bb58fda6d42fc4812c3e1eebb17ebeeb01472c6', '1b0c82717683cf1beb644c835bb58fda6d42fc4812c3e1eebb17ebeeb01472c6', (('Description', 1),), 'dbc9c3db2b39c52c1835717075e465f6ba094f64a6f8acf75f24d31b4d0582e7', 'e800023f27e85df86817dec926da20c724f295ae456b6f528c1ec130cf1169fe', 'a3ada137ff5e3a3c4a611541e002cab0cd67c51c9aeac3250731289910c33a21', 'dbc9c3db2b39c52c1835717075e465f6ba094f64a6f8acf75f24d31b4d0582e7', 'conditional-specific-form-extension', 'derivative', ('polymorph-trait', 'counteracting', 'impersonate', 'size-space-reach')),
    ('related-change-shape:voidworm', 'Voidworm', 'Protean Anatomy', '270.4', (('^.creature', 2),), (('!.Protean Anatomy', 20),), '13b8e015d13c6174ab6122ba9a1a0262b6a2df73a41e0bf4060cd48fdc52a718', '6b7174a317fc74be1fbed0695bd4fa14a39c930e3c4069a548cbcf375dcd369b', '115a3cb8b8ccea2d30045d61ccb9068a671ecd592b29f9f48eef1cf9a9ccc401', '115a3cb8b8ccea2d30045d61ccb9068a671ecd592b29f9f48eef1cf9a9ccc401', (('Description', 1), ('~.p', 0)), 'c08daae27b5b46163a19fb1e20f424e233fffc24c40ab83aae8e9136c999fe78', 'dd9e0007bae296eec55456e52b6aea59712141afc9ae6225e43d967a780f1f17', '3ebc6e5afcc2f4647ca32ddc21e8a1300fe4ee741110c233ffed0f28bb7112bb', 'c08daae27b5b46163a19fb1e20f424e233fffc24c40ab83aae8e9136c999fe78', 'lexical-near-miss', 'lexical-near-miss', ()),
)


_COMMON_PROVIDER_IDS = (
    "change-shape-glossary",
    "polymorph-trait",
    "counteracting",
    "impersonate",
    "size-space-reach",
)
_FORM_PROVIDER_IDS = (
    ("Leaf Leshy", "form-producer:leaf-leshy"),
    ("Mountain Oni", "form-producer:mountain-oni"),
    ("Nymph Queen", "form-producer:nymph-queen"),
)
_PROVIDER_PURPOSES = tuple(
    (spec[0], spec[9]) for spec in _PROVIDER_SPECS
)

_RUNTIME_DEPENDENCIES = (
    ("immutable-natural-profile", "runtime", "form-runtime", "immutable natural definition plus exact-ID active form projection"),
    ("single-active-polymorph", "runtime", "form-runtime", "one active exact-ID polymorph effect and counteract replacement gate"),
    ("transactional-size-footprint", "runtime", "form-runtime", "atomic size, occupied-square, reach, and spatial recomputation"),
    ("shared-strike-form-projection", "runtime", "form-runtime", "replacement Strikes and riders through the shared Strike resolver"),
    ("effective-profile-overlays", "runtime", "form-runtime", "Speed, traits, senses, auras, and ability availability projection"),
    ("equipment-and-object-form-policy", "runtime", "form-runtime", "gear absorption, visibility, activation, hands, and object restrictions"),
    ("impersonate-disguise-state", "runtime", "form-runtime", "generic or specific appearance and Deception observer state"),
    ("action-and-frequency-accounting", "runtime", "form-runtime", "single, two, free, and once-per-round activity accounting"),
    ("form-event-synchronization", "runtime", "form-runtime", "events, transcript, pending decisions, and digest stay synchronized"),
)
_DRYAD_DEPENDENCY = (
    "dryad-queen-trait-conflict",
    "source-link",
    "foundation",
    "adjudicate the Dryad Queen primal-only consumer against the polymorph/primal shared producer",
)
_CONCENTRATION_DEPENDENCY = (
    "concentration-spelling-adjudication",
    "source-link",
    "foundation",
    "obtain an exact provider receipt before normalizing the printed concentration trait",
)


class _SealedType(type):
    def __new__(
        metaclass: type,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, object],
        **kwargs: object,
    ) -> type:
        if any(
            base.__dict__.get("_change_shape_type_sealed", False)
            for base in bases
        ):
            raise TypeError("sealed Change Shape types cannot be subclassed")
        return super().__new__(
            metaclass,
            name,
            bases,
            namespace,
            **kwargs,
        )

    def __setattr__(cls, name: str, value: object) -> None:
        if cls.__dict__.get("_change_shape_type_sealed", False):
            raise TypeError(f"{cls.__name__} is sealed")
        super().__setattr__(name, value)

    def __delattr__(cls, name: str) -> None:
        if cls.__dict__.get("_change_shape_type_sealed", False):
            raise TypeError(f"{cls.__name__} is sealed")
        super().__delattr__(name)


def _seal_type(value: type) -> None:
    type.__setattr__(value, "_change_shape_type_sealed", True)


class _NoTransfer(metaclass=_SealedType):
    __slots__ = ()

    def __copy__(self) -> object:
        raise TypeError(f"{type(self).__name__} cannot be copied")

    def __deepcopy__(self, _memo: dict[int, object]) -> object:
        raise TypeError(f"{type(self).__name__} cannot be copied")

    def __reduce__(self) -> object:
        raise TypeError(f"{type(self).__name__} cannot be pickled")

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError(f"{type(self).__name__} cannot be pickled")


@final
@dataclass(frozen=True, slots=True, init=False)
class ChangeShapeAddressability(_NoTransfer):
    """Seven independently rederived current-authority checks."""

    locator: bool
    carrier: bool
    selection: bool
    block_hash: bool
    member_hash: bool
    value_hash: bool
    selection_hash: bool

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("ChangeShapeAddressability is compiler-created")


@final
@dataclass(frozen=True, slots=True, init=False)
class ChangeShapeDependency(_NoTransfer):
    dependency_id: str
    phase: str
    category: str
    required_contract: str

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("ChangeShapeDependency is compiler-created")


@final
@dataclass(frozen=True, slots=True, init=False)
class ChangeShapeFormReference(_NoTransfer):
    reference_id: str
    source_kind: str
    source_rule_id: str
    description_shape: str
    paragraphs: tuple[str, ...]
    description_sha256: str
    source_member_sha256: str
    source_value_sha256: str

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("ChangeShapeFormReference is compiler-created")


@final
@dataclass(frozen=True, slots=True, init=False)
class ChangeShapeTraitConflict(_NoTransfer):
    local_traits: tuple[str, ...]
    producer_traits: tuple[str, ...]
    status: str

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("ChangeShapeTraitConflict is compiler-created")


@final
@dataclass(frozen=True, slots=True, init=False)
class ChangeShapeLinkEdge(_NoTransfer):
    consumer_id: str
    producer_id: str

    def __init__(self, consumer_id: str, producer_id: str) -> None:
        if type(self) is not ChangeShapeLinkEdge:
            raise TypeError("ChangeShapeLinkEdge must be exact")
        if (
            type(consumer_id) is not str
            or not consumer_id
            or consumer_id != consumer_id.strip()
            or type(producer_id) is not str
            or not producer_id
            or producer_id != producer_id.strip()
        ):
            raise ValueError("Change Shape link IDs must be trimmed strings")
        object.__setattr__(self, "consumer_id", consumer_id)
        object.__setattr__(self, "producer_id", producer_id)


@final
@dataclass(frozen=True, slots=True, init=False)
class CompiledChangeShape(_NoTransfer):
    creature_name: str
    sequence: int
    locator: str
    cohort: str
    action_cost: ChangeShapeActionCost
    source_traits: tuple[str, ...]
    mechanic_traits: tuple[str, ...]
    description_shape: str
    paragraphs: tuple[str, ...]
    description_sha256: str
    explicit_glossary: bool
    frequency: str | None
    consumer_rule: VerifiedRuleReceipt
    provider_rules: tuple[VerifiedRuleReceipt, ...]
    local_form: ChangeShapeFormReference
    link_mode: str | None
    form_provider_rule_id: str | None
    addressability: ChangeShapeAddressability
    dependencies: tuple[ChangeShapeDependency, ...]

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("CompiledChangeShape is compiler-created")


@final
@dataclass(frozen=True, slots=True, init=False)
class LinkedChangeShape(_NoTransfer):
    compiled: CompiledChangeShape
    form_catalog: tuple[ChangeShapeFormReference, ...]
    effective_traits: tuple[str, ...] | None
    trait_conflict: ChangeShapeTraitConflict | None
    link_status: str

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("LinkedChangeShape is linker-created")


@final
@dataclass(frozen=True, slots=True, init=False)
class RelatedChangeShapeUse(_NoTransfer):
    creature_name: str
    source_label: str
    locator: str
    source_text: str
    source_scalar_sha256: str
    classification: str
    relationship: str
    consumer_rule: VerifiedRuleReceipt
    provider_rules: tuple[VerifiedRuleReceipt, ...]
    dependencies: tuple[ChangeShapeDependency, ...]

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("RelatedChangeShapeUse is compiler-created")


def _path_from_spec(
    value: tuple[tuple[str, int], ...],
) -> tuple[RawMemberStep, ...]:
    if type(value) is not tuple:
        raise AssertionError("reviewed Change Shape path must be a tuple")
    result: list[RawMemberStep] = []
    for item in value:
        if (
            type(item) is not tuple
            or len(item) != 2
            or type(item[0]) is not str
            or type(item[1]) is not int
        ):
            raise AssertionError("reviewed Change Shape path is invalid")
        result.append(
            RawMemberStep(raw_key=item[0], member_ordinal=item[1])
        )
    return tuple(result)


def _direct_requirement(spec: _DirectSpec) -> RuleRequirement:
    return RuleRequirement(
        rule_id=spec[0],
        source_id="core-mc1",
        locator=spec[3],
        carrier_path=_path_from_spec(spec[4]),
        selection_path=_path_from_spec(spec[5]),
        expected_block_sha256=spec[6],
        expected_member_sha256=spec[7],
        expected_value_sha256=spec[8],
        expected_selection_sha256=spec[9],
    )


def _provider_requirement(spec: _ProviderSpec) -> RuleRequirement:
    return RuleRequirement(
        rule_id=spec[0],
        source_id=spec[1],
        locator=spec[2],
        carrier_path=_path_from_spec(spec[3]),
        selection_path=_path_from_spec(spec[4]),
        expected_block_sha256=spec[5],
        expected_member_sha256=spec[6],
        expected_value_sha256=spec[7],
        expected_selection_sha256=spec[8],
    )


def _related_requirement(spec: _RelatedSpec) -> RuleRequirement:
    return RuleRequirement(
        rule_id=spec[0],
        source_id="core-mc1",
        locator=spec[3],
        carrier_path=_path_from_spec(spec[4]),
        selection_path=_path_from_spec(spec[5]),
        expected_block_sha256=spec[6],
        expected_member_sha256=spec[7],
        expected_value_sha256=spec[8],
        expected_selection_sha256=spec[9],
    )


def _legacy_ordered_payload(
    value: object,
    *,
    depth: int = 0,
    counter: list[int] | None = None,
    active: set[int] | None = None,
) -> object:
    """Return the packet's bounded duplicate-preserving hash payload."""

    if counter is None:
        counter = [0]
    if active is None:
        active = set()
    if depth > MAX_CHANGE_SHAPE_DEPTH:
        raise ChangeShapeCompileError(
            "ordered Change Shape source exceeds its depth bound"
        )
    counter[0] += 1
    if counter[0] > MAX_CHANGE_SHAPE_NODES:
        raise ChangeShapeCompileError(
            "ordered Change Shape source exceeds its node bound"
        )
    value_type = type(value)
    if value_type is RawSourceObject:
        identity = id(value)
        if identity in active:
            raise ChangeShapeCompileError(
                "ordered Change Shape source contains a cycle"
            )
        if type(value.members) is not tuple or any(
            type(member) is not RawSourceMember for member in value.members
        ):
            raise ChangeShapeCompileError(
                "ordered Change Shape object members are invalid"
            )
        active.add(identity)
        try:
            return {
                "$orderedObject": [
                    [
                        member.key,
                        _legacy_ordered_payload(
                            member.value,
                            depth=depth + 1,
                            counter=counter,
                            active=active,
                        ),
                    ]
                    for member in value.members
                ]
            }
        finally:
            active.remove(identity)
    if value_type is RawSourceArray:
        identity = id(value)
        if identity in active:
            raise ChangeShapeCompileError(
                "ordered Change Shape source contains a cycle"
            )
        if type(value.items) is not tuple:
            raise ChangeShapeCompileError(
                "ordered Change Shape array items are invalid"
            )
        active.add(identity)
        try:
            return [
                _legacy_ordered_payload(
                    item,
                    depth=depth + 1,
                    counter=counter,
                    active=active,
                )
                for item in value.items
            ]
        finally:
            active.remove(identity)
    if value is None or value_type in (bool, int, float, str):
        return value
    raise ChangeShapeCompileError(
        "ordered Change Shape source contains an unsupported value"
    )


def _legacy_source_sha256(value: object) -> str:
    try:
        encoded = json.dumps(
            _legacy_ordered_payload(value),
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as failure:
        raise ChangeShapeCompileError(
            "ordered Change Shape source is not finite JSON"
        ) from failure
    if len(encoded) > MAX_CHANGE_SHAPE_TEXT_BYTES * 32:
        raise ChangeShapeCompileError(
            "ordered Change Shape source exceeds its byte bound"
        )
    return hashlib.sha256(encoded).hexdigest()


def _legacy_member_sha256(member: RawSourceMember) -> str:
    if type(member) is not RawSourceMember:
        raise ChangeShapeCompileError(
            "Change Shape selection did not retain an exact raw member"
        )
    return _legacy_source_sha256(RawSourceObject(members=(member,)))


def _unique_member(
    value: RawSourceObject,
    raw_key: str,
) -> RawSourceMember:
    if (
        type(value) is not RawSourceObject
        or type(value.members) is not tuple
    ):
        raise ChangeShapeCompileError(
            "Change Shape source carrier must be an exact raw object"
        )
    matches = tuple(
        member
        for member in value.members
        if type(member) is RawSourceMember and member.key == raw_key
    )
    if len(matches) != 1:
        raise ChangeShapeCompileError(
            f"Change Shape source requires one {raw_key!r} member"
        )
    return matches[0]


def _description_parts(value: object) -> tuple[str, tuple[str, ...]]:
    if type(value) is str:
        if (
            not value
            or value != value.strip()
            or len(value.encode("utf-8")) > MAX_CHANGE_SHAPE_TEXT_BYTES
        ):
            raise ChangeShapeCompileError(
                "Change Shape description text is invalid"
            )
        return "string", (value,)
    if (
        type(value) is not RawSourceObject
        or type(value.members) is not tuple
        or not value.members
    ):
        raise ChangeShapeCompileError(
            "Change Shape description has an unsupported source shape"
        )
    parts: list[str] = []
    total = 0
    for member in value.members:
        if (
            type(member) is not RawSourceMember
            or member.key != "~.p"
            or type(member.value) is not str
            or not member.value
            or member.value != member.value.strip()
        ):
            raise ChangeShapeCompileError(
                "ordered Change Shape description flow is invalid"
            )
        total += len(member.value.encode("utf-8"))
        if total > MAX_CHANGE_SHAPE_TEXT_BYTES:
            raise ChangeShapeCompileError(
                "Change Shape description exceeds its byte bound"
            )
        parts.append(member.value)
    return "ordered-paragraph-flow", tuple(parts)


_FREQUENCY_RE = re.compile(r"^Frequency ([^;]+); Effect ", re.ASCII)
_ALLOWED_TRAIT_TUPLES = (
    ("arcane", "concentrate", "polymorph"),
    ("concentrate", "divine", "polymorph"),
    ("concentrate", "occult", "polymorph"),
    ("concentrate", "polymorph", "primal"),
    ("concentration", "divine", "polymorph"),
    ("polymorph", "primal"),
    ("primal",),
)


def _parse_direct_source(
    selection: VerifiedSourceSelection,
    spec: _DirectSpec,
) -> tuple[
    ChangeShapeActionCost,
    tuple[str, ...],
    str,
    tuple[str, ...],
    bool,
    str | None,
]:
    if type(selection) is not VerifiedSourceSelection:
        raise TypeError(
            "direct Change Shape source must be an exact verified selection"
        )
    raw_member = selection.raw_member
    adjacent_field_repair = spec[0] == "change-shape-consumer:006"
    surrounding_block_rebind = spec[0] in {
        "change-shape-consumer:039",
        "change-shape-consumer:199",
        "change-shape-consumer:271",
    }
    expected_member_keys = (
        ("Action", "Traits", "Frequency", "Effect")
        if adjacent_field_repair
        else ("Action", "Traits", "Description")
    )
    if (
        type(raw_member) is not RawSourceMember
        or raw_member.key != "!.Change Shape"
        or type(raw_member.value) is not RawSourceObject
        or type(raw_member.value.members) is not tuple
        or tuple(member.key for member in raw_member.value.members)
        != expected_member_keys
        or selection.selected_value is not raw_member.value
    ):
        raise ChangeShapeCompileError(
            "direct Change Shape member differs from its reviewed shape"
        )
    action_value = raw_member.value.members[0].value
    action: ChangeShapeActionCost
    if action_value == "single" and type(action_value) is str:
        action = 1
    elif action_value == "two" and type(action_value) is str:
        action = 2
    elif action_value == "free" and type(action_value) is str:
        action = "free"
    else:
        raise ChangeShapeCompileError(
            "direct Change Shape action cost is invalid"
        )
    raw_traits = raw_member.value.members[1].value
    if (
        type(raw_traits) is not RawSourceArray
        or type(raw_traits.items) is not tuple
        or any(type(item) is not str for item in raw_traits.items)
        or raw_traits.items not in _ALLOWED_TRAIT_TUPLES
    ):
        raise ChangeShapeCompileError(
            "direct Change Shape traits are outside the reviewed grammar"
        )
    if adjacent_field_repair:
        frequency_value = raw_member.value.members[2].value
        if type(frequency_value) is not str:
            raise ChangeShapeCompileError(
                "direct Change Shape frequency is invalid"
            )
        frequency = frequency_value
        description = raw_member.value.members[3].value
    else:
        frequency = None
        description = raw_member.value.members[2].value
    shape, paragraphs = _description_parts(description)
    explicit_glossary = any("(page 358)" in item for item in paragraphs)
    if not adjacent_field_repair:
        match = (
            _FREQUENCY_RE.match(paragraphs[0])
            if shape == "string"
            else None
        )
        frequency = None if match is None else match.group(1)
    name_member = _unique_member(selection.carrier.raw_block, "Name")
    if (
        type(name_member.value) is not str
        or name_member.value != spec[2]
        or action != spec[15]
        or shape != spec[16]
        or explicit_glossary is not spec[17]
        or frequency != spec[18]
        or (
            not adjacent_field_repair
            and (
                (
                    not surrounding_block_rebind
                    and _legacy_source_sha256(
                        selection.carrier.raw_block
                    )
                    != spec[10]
                )
                or _legacy_member_sha256(raw_member) != spec[11]
                or _legacy_source_sha256(raw_member.value) != spec[12]
                or _legacy_source_sha256(description) != spec[13]
            )
        )
    ):
        raise ChangeShapeCompileError(
            "direct Change Shape source differs from reviewed evidence"
        )
    return (
        action,
        tuple(raw_traits.items),
        shape,
        paragraphs,
        explicit_glossary,
        frequency,
    )


def _raw_value_at_path(
    value: object,
    path_spec: tuple[tuple[str, int], ...],
) -> object:
    current = value
    for raw_key, member_ordinal in path_spec:
        if (
            type(current) is not RawSourceObject
            or type(current.members) is not tuple
            or member_ordinal < 0
            or member_ordinal >= len(current.members)
        ):
            raise ChangeShapeCompileError(
                "related Change Shape scalar path leaves its source object"
            )
        member = current.members[member_ordinal]
        if (
            type(member) is not RawSourceMember
            or member.key != raw_key
        ):
            raise ChangeShapeCompileError(
                "related Change Shape scalar path disagrees with authority"
            )
        current = member.value
    return current


def _same_requirement(
    left: RuleRequirement,
    right: RuleRequirement,
) -> bool:
    return canonical_json_bytes(
        RuleRequirement.as_serialized(left)
    ) == canonical_json_bytes(
        RuleRequirement.as_serialized(right)
    )


def _same_receipt(left: SourceReceipt, right: SourceReceipt) -> bool:
    return canonical_json_bytes(
        SourceReceipt.as_serialized(left)
    ) == canonical_json_bytes(
        SourceReceipt.as_serialized(right)
    )


def _new_artifact(artifact_type: type, values: tuple[object, ...]) -> object:
    slots = artifact_type.__slots__
    if type(slots) is not tuple or len(slots) != len(values):
        raise AssertionError("Change Shape artifact factory is inconsistent")
    result = object.__new__(artifact_type)
    for field_name, value in zip(slots, values, strict=True):
        object.__setattr__(result, field_name, value)
    return result


def _dependency(
    spec: tuple[str, str, str, str],
    dependency_type: type[ChangeShapeDependency],
) -> ChangeShapeDependency:
    return _new_artifact(dependency_type, spec)  # type: ignore[return-value]


def _addressability(
    addressability_type: type[ChangeShapeAddressability],
) -> ChangeShapeAddressability:
    return _new_artifact(
        addressability_type,
        (True, True, True, True, True, True, True),
    )  # type: ignore[return-value]


def _provider_spec(
    rule_id: str,
    specs: tuple[_ProviderSpec, ...],
) -> _ProviderSpec:
    matches = tuple(spec for spec in specs if spec[0] == rule_id)
    if len(matches) != 1:
        raise AssertionError(
            f"reviewed Change Shape provider is missing: {rule_id}"
        )
    return matches[0]


def _form_provider_id(
    producer_name: str,
    pairs: tuple[tuple[str, str], ...],
) -> str:
    matches = tuple(
        rule_id for name, rule_id in pairs if name == producer_name
    )
    if len(matches) != 1:
        raise AssertionError(
            f"reviewed Change Shape form producer is missing: {producer_name}"
        )
    return matches[0]


def _provider_purpose(
    rule_id: str,
    purposes: tuple[tuple[object, object], ...],
) -> str:
    matches = tuple(
        purpose
        for candidate, purpose in purposes
        if candidate == rule_id and type(purpose) is str
    )
    if len(matches) != 1:
        raise AssertionError(
            f"reviewed Change Shape provider purpose is missing: {rule_id}"
        )
    return matches[0]


def _require_initialized(
    value: object,
    artifact_type: type,
    label: str,
) -> None:
    if type(value) is not artifact_type:
        raise TypeError(f"{label} must use the exact canonical type")
    try:
        for field_name in artifact_type.__slots__:
            object.__getattribute__(value, field_name)
    except AttributeError as failure:
        raise ChangeShapeCompileError(f"{label} is uninitialized") from failure


def _require_text(value: object, label: str) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value.encode("utf-8")) > MAX_CHANGE_SHAPE_TEXT_BYTES
    ):
        raise ChangeShapeCompileError(
            f"{label} must be bounded, non-empty, trimmed text"
        )
    return value


def _validate_link_edges(
    edges: tuple[ChangeShapeLinkEdge, ...],
    edge_type: type[ChangeShapeLinkEdge],
    *,
    maximum_links: int,
    maximum_depth: int,
) -> None:
    if (
        type(edges) is not tuple
        or len(edges) > maximum_links
        or any(type(edge) is not edge_type for edge in edges)
    ):
        raise TypeError(
            "Change Shape link graph must be a bounded tuple of exact edges"
        )
    graph: dict[str, str] = {}
    for edge in edges:
        _require_initialized(edge, edge_type, "Change Shape link edge")
        consumer = _require_text(edge.consumer_id, "link consumer")
        producer = _require_text(edge.producer_id, "link producer")
        if consumer in graph:
            raise ChangeShapeLinkError(
                f"ambiguous Change Shape producer for {consumer}"
            )
        graph[consumer] = producer
    for start in graph:
        seen: set[str] = set()
        cursor = start
        depth = 0
        while cursor in graph:
            if cursor in seen:
                raise ChangeShapeLinkError("Change Shape form alias cycle")
            seen.add(cursor)
            depth += 1
            if depth > maximum_depth:
                raise ChangeShapeLinkError(
                    "Change Shape form graph exceeds its depth bound"
                )
            cursor = graph[cursor]


def _bind_reviewed_api(
    direct_specs: tuple[_DirectSpec, ...],
    provider_specs: tuple[_ProviderSpec, ...],
    related_specs: tuple[_RelatedSpec, ...],
    form_provider_pairs: tuple[tuple[str, str], ...],
    provider_purposes: tuple[tuple[object, object], ...],
    runtime_dependency_specs: tuple[tuple[str, str, str, str], ...],
    dryad_dependency_spec: tuple[str, str, str, str],
    concentration_dependency_spec: tuple[str, str, str, str],
    *,
    compiled_type: type[CompiledChangeShape],
    linked_type: type[LinkedChangeShape],
    related_type: type[RelatedChangeShapeUse],
    form_type: type[ChangeShapeFormReference],
    dependency_type: type[ChangeShapeDependency],
    addressability_type: type[ChangeShapeAddressability],
    conflict_type: type[ChangeShapeTraitConflict],
    edge_type: type[ChangeShapeLinkEdge],
) -> tuple[Callable[..., Any], ...]:
    """Close every public operation over immutable reviewed primitives."""

    adapter_reload = SourceAuthorityAdapter.reload
    adapter_validate_selection = SourceAuthorityAdapter.validate_selection
    adapter_resolve_rule = SourceAuthorityAdapter.resolve_rule
    adapter_validate_rule = SourceAuthorityAdapter.validate_rule
    adapter_require_shared = SourceAuthorityAdapter.require_shared_authority
    verified_rule_serialize = VerifiedRuleReceipt.as_serialized
    authority_contract = SourceAuthorityAdapter
    source_receipt_contract = SourceReceipt
    verified_rule_contract = VerifiedRuleReceipt
    raw_object_contract = RawSourceObject
    raw_array_contract = RawSourceArray
    unique_member_impl = _unique_member
    common_provider_ids = _COMMON_PROVIDER_IDS
    maximum_form_links = MAX_CHANGE_SHAPE_LINKS

    direct_requirement_impl = _direct_requirement
    provider_requirement_impl = _provider_requirement
    related_requirement_impl = _related_requirement
    parse_direct_impl = _parse_direct_source
    legacy_source_hash_impl = _legacy_source_sha256
    legacy_member_hash_impl = _legacy_member_sha256
    raw_value_at_path_impl = _raw_value_at_path
    same_requirement_impl = _same_requirement
    same_receipt_impl = _same_receipt
    new_artifact_impl = _new_artifact
    dependency_impl = _dependency
    addressability_impl = _addressability
    provider_spec_impl = _provider_spec
    form_provider_id_impl = _form_provider_id
    provider_purpose_impl = _provider_purpose
    require_initialized_impl = _require_initialized
    require_text_impl = _require_text
    description_parts_impl = _description_parts
    validate_edges_impl = _validate_link_edges
    canonical_json_impl = canonical_json_bytes

    def _require_authority(
        authority: SourceAuthorityAdapter,
    ) -> SourceAuthorityAdapter:
        if type(authority) is not authority_contract:
            raise TypeError(
                "Change Shape operations require SourceAuthorityAdapter"
            )
        return authority

    def _resolve_provider(
        authority: SourceAuthorityAdapter,
        rule_id: str,
    ) -> VerifiedRuleReceipt:
        spec = provider_spec_impl(rule_id, provider_specs)
        expected = provider_requirement_impl(spec)
        verified = adapter_validate_rule(
            authority,
            adapter_resolve_rule(authority, expected),
        )
        if (
            verified.rule_id != rule_id
            or not same_requirement_impl(verified.requirement, expected)
        ):
            raise ChangeShapeCompileError(
                f"provider differs from reviewed authority: {rule_id}"
            )
        return verified

    def _consumer_and_spec(
        authority: SourceAuthorityAdapter,
        receipt: SourceReceipt,
    ) -> tuple[VerifiedSourceSelection, VerifiedRuleReceipt, _DirectSpec]:
        _require_authority(authority)
        if type(receipt) is not source_receipt_contract:
            raise TypeError(
                "Change Shape compilation requires an exact SourceReceipt"
            )
        consumer = adapter_validate_selection(
            authority,
            adapter_reload(authority, receipt),
        )
        candidates = tuple(
            spec
            for spec in direct_specs
            if spec[3] == consumer.address.locator
            and consumer.address.source_id == "core-mc1"
        )
        matches: list[tuple[VerifiedRuleReceipt, _DirectSpec]] = []
        for spec in candidates:
            rule = adapter_validate_rule(
                authority,
                adapter_resolve_rule(
                    authority,
                    direct_requirement_impl(spec),
                ),
            )
            if same_receipt_impl(rule.receipt, consumer.receipt):
                matches.append((rule, spec))
        if len(matches) != 1:
            raise ChangeShapeCompileError(
                "source is not one exact reviewed Change Shape carrier"
            )
        consumer_rule, spec = matches[0]
        adapter_require_shared(authority, consumer, (consumer_rule,))
        return consumer, consumer_rule, spec

    def _expected_direct_provider_ids(
        spec: _DirectSpec,
    ) -> tuple[str, ...]:
        ids = [*common_provider_ids]
        extra = spec[20]
        if type(extra) is not tuple or any(
            type(item) is not str for item in extra
        ):
            raise AssertionError("reviewed Change Shape rules are invalid")
        ids.extend(extra)
        link = spec[19]
        if link is not None:
            if (
                type(link) is not tuple
                or len(link) != 2
                or type(link[0]) is not str
                or type(link[1]) is not str
            ):
                raise AssertionError(
                    "reviewed Change Shape link is invalid"
                )
            ids.append(
                form_provider_id_impl(link[1], form_provider_pairs)
            )
        return tuple(ids)

    def _resolve_providers(
        authority: SourceAuthorityAdapter,
        consumer: VerifiedSourceSelection,
        consumer_rule: VerifiedRuleReceipt,
        provider_ids: tuple[str, ...],
    ) -> tuple[VerifiedRuleReceipt, ...]:
        providers = tuple(
            _resolve_provider(authority, rule_id)
            for rule_id in provider_ids
        )
        adapter_require_shared(
            authority,
            consumer,
            (consumer_rule, *providers),
        )
        return providers

    def _dependency_tuple(
        provider_ids: tuple[str, ...],
        creature_name: str,
    ) -> tuple[ChangeShapeDependency, ...]:
        result = [
            dependency_impl(
                (
                    rule_id,
                    "source-link",
                    "source-rule",
                    provider_purpose_impl(rule_id, provider_purposes),
                ),
                dependency_type,
            )
            for rule_id in provider_ids
        ]
        if creature_name == "Dryad Queen":
            result.append(
                dependency_impl(dryad_dependency_spec, dependency_type)
            )
        if creature_name == "Voidworm":
            result.append(
                dependency_impl(
                    concentration_dependency_spec,
                    dependency_type,
                )
            )
        result.extend(
            dependency_impl(spec, dependency_type)
            for spec in runtime_dependency_specs
        )
        return tuple(result)

    def _form_reference(
        rule: VerifiedRuleReceipt,
        source_kind: str,
        source_rule_id: str,
    ) -> ChangeShapeFormReference:
        selection = rule.selection
        raw = selection.selected_value
        if type(raw) is not raw_object_contract:
            raise ChangeShapeCompileError(
                "Change Shape form provider must select an object"
            )
        description_member = unique_member_impl(
            raw,
            "Effect"
            if source_rule_id == "change-shape-consumer:006"
            else "Description",
        )
        shape, paragraphs = description_parts_impl(
            description_member.value
        )
        member_sha = selection.member_sha256
        if type(member_sha) is not str:
            raise ChangeShapeCompileError(
                "Change Shape form provider lacks a member digest"
            )
        return new_artifact_impl(
            form_type,
            (
                f"{source_kind}:{rule.receipt.digest}",
                source_kind,
                source_rule_id,
                shape,
                paragraphs,
                legacy_source_hash_impl(description_member.value),
                member_sha,
                selection.value_sha256,
            ),
        )  # type: ignore[return-value]

    def _canonical_compiled(
        spec: _DirectSpec,
        consumer_rule: VerifiedRuleReceipt,
        providers: tuple[VerifiedRuleReceipt, ...],
    ) -> CompiledChangeShape:
        (
            action,
            source_traits,
            description_shape,
            paragraphs,
            explicit_glossary,
            frequency,
        ) = parse_direct_impl(consumer_rule.selection, spec)
        provider_ids = tuple(item.rule_id for item in providers)
        if provider_ids != _expected_direct_provider_ids(spec):
            raise ChangeShapeCompileError(
                "Change Shape provider order differs from review"
            )
        link = spec[19]
        link_mode = None if link is None else link[0]
        form_provider_rule_id = (
            None
            if link is None
            else form_provider_id_impl(link[1], form_provider_pairs)
        )
        return new_artifact_impl(
            compiled_type,
            (
                spec[2],
                spec[1],
                spec[3],
                spec[14],
                action,
                source_traits,
                # "concentration" is retained until an exact normalization
                # provider exists; the typed dependency blocks activation.
                source_traits,
                description_shape,
                paragraphs,
                spec[13],
                explicit_glossary,
                frequency,
                consumer_rule,
                providers,
                _form_reference(
                    consumer_rule,
                    "local-description",
                    consumer_rule.rule_id,
                ),
                link_mode,
                form_provider_rule_id,
                addressability_impl(addressability_type),
                _dependency_tuple(provider_ids, spec[2]),
            ),
        )  # type: ignore[return-value]

    def _dependency_payload(
        value: ChangeShapeDependency,
    ) -> dict[str, str]:
        require_initialized_impl(
            value,
            dependency_type,
            "Change Shape dependency",
        )
        return {
            "id": require_text_impl(value.dependency_id, "dependency id"),
            "phase": require_text_impl(value.phase, "dependency phase"),
            "category": require_text_impl(
                value.category,
                "dependency category",
            ),
            "requiredContract": require_text_impl(
                value.required_contract,
                "dependency contract",
            ),
            "status": "deferred",
            "blocks": "registry-activation",
        }

    def _form_payload(
        value: ChangeShapeFormReference,
    ) -> dict[str, Any]:
        require_initialized_impl(
            value,
            form_type,
            "Change Shape form reference",
        )
        if (
            type(value.paragraphs) is not tuple
            or not value.paragraphs
            or any(type(item) is not str for item in value.paragraphs)
        ):
            raise ChangeShapeCompileError(
                "Change Shape form paragraphs are invalid"
            )
        return {
            "id": require_text_impl(value.reference_id, "form id"),
            "sourceKind": require_text_impl(
                value.source_kind,
                "form source kind",
            ),
            "sourceRuleId": require_text_impl(
                value.source_rule_id,
                "form source rule",
            ),
            "description": {
                "shape": require_text_impl(
                    value.description_shape,
                    "form description shape",
                ),
                "paragraphs": list(value.paragraphs),
                "sha256": require_text_impl(
                    value.description_sha256,
                    "form description digest",
                ),
            },
            "sourceMemberSha256": require_text_impl(
                value.source_member_sha256,
                "form member digest",
            ),
            "sourceValueSha256": require_text_impl(
                value.source_value_sha256,
                "form value digest",
            ),
            "status": "unresolved-form-profile",
        }

    def _addressability_payload(
        value: ChangeShapeAddressability,
    ) -> dict[str, bool]:
        require_initialized_impl(
            value,
            addressability_type,
            "Change Shape addressability",
        )
        flags = (
            value.locator,
            value.carrier,
            value.selection,
            value.block_hash,
            value.member_hash,
            value.value_hash,
            value.selection_hash,
        )
        if any(type(flag) is not bool or not flag for flag in flags):
            raise ChangeShapeCompileError(
                "Change Shape addressability must be freshly verified"
            )
        return {
            "locator": flags[0],
            "carrier": flags[1],
            "selection": flags[2],
            "blockHash": flags[3],
            "memberHash": flags[4],
            "valueHash": flags[5],
            "selectionHash": flags[6],
        }

    def _compiled_payload(
        value: CompiledChangeShape,
        spec: _DirectSpec,
    ) -> dict[str, Any]:
        return {
            "family": "change-shape",
            "mechanicType": "change-shape",
            "creature": value.creature_name,
            "sequence": value.sequence,
            "sourceId": "core-mc1",
            "locator": value.locator,
            "cohort": value.cohort,
            "actionCost": value.action_cost,
            "sourceTraits": list(value.source_traits),
            "traits": list(value.mechanic_traits),
            "traitNormalization": "deferred"
            if value.creature_name == "Voidworm"
            else "literal",
            "frequency": value.frequency,
            "duration": "indefinite",
            "naturalFormId": "natural",
            "description": {
                "shape": value.description_shape,
                "paragraphs": list(value.paragraphs),
                "sha256": value.description_sha256,
                "explicitGlossaryPage358": value.explicit_glossary,
            },
            "localForm": _form_payload(value.local_form),
            "formLink": (
                None
                if value.link_mode is None
                else {
                    "mode": value.link_mode,
                    "providerRuleId": value.form_provider_rule_id,
                }
            ),
            "source": {
                "consumerRule": verified_rule_serialize(
                    value.consumer_rule
                ),
                "legacyOrderedBlockSha256": spec[10],
                "legacyRawMemberSha256": spec[11],
                "legacyRawValueSha256": spec[12],
                "addressability": _addressability_payload(
                    value.addressability
                ),
                "affectedByLegacyAddressabilityPlan": False,
            },
            "providerRules": [
                verified_rule_serialize(item)
                for item in value.provider_rules
            ],
            "deferredMechanics": [
                _dependency_payload(item) for item in value.dependencies
            ],
            "runtimeSupported": False,
            "registryStatus": "unregistered",
            "activationStatus": "deferred",
        }

    def _validated_rule_surface(
        authority: SourceAuthorityAdapter,
        value: object,
        label: str,
    ) -> VerifiedRuleReceipt:
        if type(value) is not verified_rule_contract:
            raise TypeError(f"{label} must be an exact VerifiedRuleReceipt")
        try:
            for field_name in (
                "rule_id",
                "requirement",
                "selection",
                "receipt",
                "_capability",
            ):
                object.__getattribute__(value, field_name)
        except AttributeError as failure:
            raise ChangeShapeCompileError(
                f"{label} is uninitialized"
            ) from failure
        return adapter_validate_rule(authority, value)

    def _validate_compiled(
        authority: SourceAuthorityAdapter,
        value: CompiledChangeShape,
    ) -> tuple[_DirectSpec, dict[str, Any]]:
        _require_authority(authority)
        require_initialized_impl(
            value,
            compiled_type,
            "compiled Change Shape",
        )
        consumer_rule = _validated_rule_surface(
            authority,
            value.consumer_rule,
            "Change Shape consumer rule",
        )
        matches = tuple(
            spec for spec in direct_specs if spec[0] == consumer_rule.rule_id
        )
        if len(matches) != 1:
            raise ChangeShapeCompileError(
                "compiled Change Shape consumer is outside the census"
            )
        spec = matches[0]
        expected_consumer = direct_requirement_impl(spec)
        if not same_requirement_impl(
            consumer_rule.requirement,
            expected_consumer,
        ):
            raise ChangeShapeCompileError(
                "compiled Change Shape retained the wrong consumer"
            )
        consumer = adapter_validate_selection(
            authority,
            consumer_rule.selection,
        )
        parse_direct_impl(consumer, spec)
        if type(value.provider_rules) is not tuple:
            raise TypeError(
                "compiled Change Shape providers must be an exact tuple"
            )
        expected_ids = _expected_direct_provider_ids(spec)
        if (
            tuple(
                item.rule_id
                for item in value.provider_rules
                if type(item) is verified_rule_contract
            )
            != expected_ids
            or len(value.provider_rules) != len(expected_ids)
        ):
            raise ChangeShapeCompileError(
                "compiled Change Shape provider order is invalid"
            )
        verified_providers: list[VerifiedRuleReceipt] = []
        for provider in value.provider_rules:
            verified = _validated_rule_surface(
                authority,
                provider,
                "Change Shape provider rule",
            )
            expected = provider_requirement_impl(
                provider_spec_impl(verified.rule_id, provider_specs)
            )
            if not same_requirement_impl(verified.requirement, expected):
                raise ChangeShapeCompileError(
                    "compiled Change Shape retained the wrong provider"
                )
            verified_providers.append(verified)
        providers = tuple(verified_providers)
        adapter_require_shared(
            authority,
            consumer,
            (consumer_rule, *providers),
        )
        canonical = _canonical_compiled(spec, consumer_rule, providers)
        supplied_payload = _compiled_payload(value, spec)
        canonical_payload = _compiled_payload(canonical, spec)
        canonical_json_impl(supplied_payload)
        if canonical_json_impl(supplied_payload) != canonical_json_impl(
            canonical_payload
        ):
            raise ChangeShapeCompileError(
                "compiled Change Shape differs from current source"
            )
        return spec, supplied_payload

    def _canonical_link(
        compiled: CompiledChangeShape,
    ) -> LinkedChangeShape:
        if compiled.form_provider_rule_id is None:
            forms = (compiled.local_form,)
            effective_traits: tuple[str, ...] | None = (
                compiled.mechanic_traits
            )
            conflict = None
            status = "linked-compile-only"
        else:
            matches = tuple(
                rule
                for rule in compiled.provider_rules
                if rule.rule_id == compiled.form_provider_rule_id
            )
            if len(matches) != 1:
                raise ChangeShapeLinkError(
                    "Change Shape form producer receipt is missing"
                )
            producer_rule = matches[0]
            source_kind = (
                "shared-section"
                if producer_rule.rule_id == "form-producer:nymph-queen"
                else "local-ability"
            )
            producer_form = _form_reference(
                producer_rule,
                source_kind,
                producer_rule.rule_id,
            )
            if compiled.link_mode == "exact-alias":
                forms = (producer_form,)
            elif compiled.link_mode in (
                "base-plus-form-override",
                "enclosing-shared-producer",
            ):
                forms = (producer_form, compiled.local_form)
            else:
                raise ChangeShapeLinkError(
                    "Change Shape form link mode is invalid"
                )
            producer_raw = producer_rule.selection.selected_value
            if type(producer_raw) is not raw_object_contract:
                raise ChangeShapeLinkError(
                    "Change Shape producer source is not an object"
                )
            traits_member = unique_member_impl(producer_raw, "Traits")
            producer_traits_raw = traits_member.value
            if (
                type(producer_traits_raw) is not raw_array_contract
                or type(producer_traits_raw.items) is not tuple
                or any(
                    type(item) is not str
                    for item in producer_traits_raw.items
                )
            ):
                raise ChangeShapeLinkError(
                    "Change Shape producer traits are invalid"
                )
            producer_traits = tuple(producer_traits_raw.items)
            if compiled.creature_name == "Dryad Queen":
                conflict = new_artifact_impl(
                    conflict_type,
                    (
                        compiled.mechanic_traits,
                        producer_traits,
                        "explicit-unadjudicated-conflict",
                    ),
                )
                effective_traits = None
                status = "explicit-unadjudicated-conflict"
            else:
                conflict = None
                if (
                    compiled.link_mode == "enclosing-shared-producer"
                    and compiled.mechanic_traits != producer_traits
                ):
                    raise ChangeShapeLinkError(
                        "unreviewed shared-producer trait conflict"
                    )
                effective_traits = (
                    producer_traits
                    if compiled.link_mode == "enclosing-shared-producer"
                    else compiled.mechanic_traits
                )
                status = "linked-compile-only"
        return new_artifact_impl(
            linked_type,
            (compiled, forms, effective_traits, conflict, status),
        )  # type: ignore[return-value]

    def _conflict_payload(
        value: ChangeShapeTraitConflict,
    ) -> dict[str, Any]:
        require_initialized_impl(
            value,
            conflict_type,
            "Change Shape trait conflict",
        )
        if (
            type(value.local_traits) is not tuple
            or type(value.producer_traits) is not tuple
            or any(type(item) is not str for item in value.local_traits)
            or any(type(item) is not str for item in value.producer_traits)
            or value.status != "explicit-unadjudicated-conflict"
        ):
            raise ChangeShapeLinkError(
                "Change Shape trait conflict is invalid"
            )
        return {
            "localTraits": list(value.local_traits),
            "producerTraits": list(value.producer_traits),
            "status": value.status,
        }

    def _linked_payload(
        value: LinkedChangeShape,
        compiled_payload: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            **compiled_payload,
            "forms": [_form_payload(item) for item in value.form_catalog],
            "effectiveTraits": (
                None
                if value.effective_traits is None
                else list(value.effective_traits)
            ),
            "traitConflict": (
                None
                if value.trait_conflict is None
                else _conflict_payload(value.trait_conflict)
            ),
            "linkStatus": value.link_status,
        }

    def _validate_linked(
        authority: SourceAuthorityAdapter,
        value: LinkedChangeShape,
    ) -> dict[str, Any]:
        _require_authority(authority)
        require_initialized_impl(value, linked_type, "linked Change Shape")
        _spec, compiled_payload = _validate_compiled(
            authority,
            value.compiled,
        )
        if (
            type(value.form_catalog) is not tuple
            or not value.form_catalog
            or len(value.form_catalog) > maximum_form_links
            or any(type(item) is not form_type for item in value.form_catalog)
        ):
            raise ChangeShapeLinkError(
                "linked Change Shape form catalog is invalid"
            )
        canonical = _canonical_link(value.compiled)
        supplied_payload = _linked_payload(value, compiled_payload)
        canonical_payload = _linked_payload(canonical, compiled_payload)
        if canonical_json_impl(supplied_payload) != canonical_json_impl(
            canonical_payload
        ):
            raise ChangeShapeLinkError(
                "linked Change Shape differs from current source"
            )
        return supplied_payload

    def _related_consumer_and_spec(
        authority: SourceAuthorityAdapter,
        receipt: SourceReceipt,
    ) -> tuple[VerifiedSourceSelection, VerifiedRuleReceipt, _RelatedSpec]:
        _require_authority(authority)
        if type(receipt) is not source_receipt_contract:
            raise TypeError(
                "related Change Shape compilation requires SourceReceipt"
            )
        consumer = adapter_validate_selection(
            authority,
            adapter_reload(authority, receipt),
        )
        candidates = tuple(
            spec
            for spec in related_specs
            if spec[3] == consumer.address.locator
            and consumer.address.source_id == "core-mc1"
        )
        matches: list[tuple[VerifiedRuleReceipt, _RelatedSpec]] = []
        for spec in candidates:
            rule = adapter_validate_rule(
                authority,
                adapter_resolve_rule(
                    authority,
                    related_requirement_impl(spec),
                ),
            )
            if same_receipt_impl(rule.receipt, consumer.receipt):
                matches.append((rule, spec))
        if len(matches) != 1:
            raise ChangeShapeCompileError(
                "source is not one reviewed related Change Shape use"
            )
        consumer_rule, spec = matches[0]
        adapter_require_shared(authority, consumer, (consumer_rule,))
        return consumer, consumer_rule, spec

    def _parse_related(
        selection: VerifiedSourceSelection,
        spec: _RelatedSpec,
    ) -> str:
        raw_member = selection.raw_member
        if (
            type(raw_member) is not RawSourceMember
            or raw_member.key != f"!.{spec[2]}"
            or type(raw_member.value) is not RawSourceObject
        ):
            raise ChangeShapeCompileError(
                "related Change Shape ability shape is invalid"
            )
        name_member = unique_member_impl(
            selection.carrier.raw_block,
            "Name",
        )
        scalar = raw_value_at_path_impl(raw_member.value, spec[10])
        if (
            type(name_member.value) is not str
            or name_member.value != spec[1]
            or type(scalar) is not str
            or not scalar
            or scalar != scalar.strip()
            or legacy_member_hash_impl(raw_member) != spec[12]
            or legacy_source_hash_impl(raw_member.value) != spec[13]
            or legacy_source_hash_impl(scalar) != spec[14]
            or legacy_source_hash_impl(scalar) != spec[11]
        ):
            raise ChangeShapeCompileError(
                "related Change Shape use differs from reviewed evidence"
            )
        return scalar

    def _related_provider_ids(spec: _RelatedSpec) -> tuple[str, ...]:
        ids = spec[17]
        if type(ids) is not tuple or any(
            type(item) is not str for item in ids
        ):
            raise AssertionError(
                "reviewed related Change Shape providers are invalid"
            )
        return () if spec[16] == "lexical-near-miss" else (
            "change-shape-glossary",
            *ids,
        )

    def _canonical_related(
        spec: _RelatedSpec,
        consumer_rule: VerifiedRuleReceipt,
        providers: tuple[VerifiedRuleReceipt, ...],
    ) -> RelatedChangeShapeUse:
        source_text = _parse_related(consumer_rule.selection, spec)
        provider_ids = tuple(item.rule_id for item in providers)
        if provider_ids != _related_provider_ids(spec):
            raise ChangeShapeCompileError(
                "related Change Shape provider order differs from review"
            )
        dependencies = (
            ()
            if spec[16] == "lexical-near-miss"
            else tuple(
                dependency_impl(
                    (
                        rule_id,
                        "source-link",
                        "source-rule",
                        provider_purpose_impl(
                            rule_id,
                            provider_purposes,
                        ),
                    ),
                    dependency_type,
                )
                for rule_id in provider_ids
            )
            + tuple(
                dependency_impl(item, dependency_type)
                for item in runtime_dependency_specs
            )
        )
        return new_artifact_impl(
            related_type,
            (
                spec[1],
                spec[2],
                spec[3],
                source_text,
                spec[14],
                spec[15],
                spec[16],
                consumer_rule,
                providers,
                dependencies,
            ),
        )  # type: ignore[return-value]

    def _related_payload(
        value: RelatedChangeShapeUse,
        spec: _RelatedSpec,
    ) -> dict[str, Any]:
        return {
            "family": "change-shape-related-use",
            "sourceId": "core-mc1",
            "creature": value.creature_name,
            "sourceLabel": value.source_label,
            "locator": value.locator,
            "sourceText": value.source_text,
            "sourceScalarSha256": value.source_scalar_sha256,
            "classification": value.classification,
            "relationship": value.relationship,
            "consumerRule": verified_rule_serialize(value.consumer_rule),
            "providerRules": [
                verified_rule_serialize(item)
                for item in value.provider_rules
            ],
            "legacyRawMemberSha256": spec[12],
            "legacyRawValueSha256": spec[13],
            "deferredMechanics": [
                _dependency_payload(item) for item in value.dependencies
            ],
            "directChangeShapeMatch": False,
            "runtimeSupported": False,
            "registryStatus": "unregistered",
            "activationStatus": "deferred",
        }

    def _validate_related(
        authority: SourceAuthorityAdapter,
        value: RelatedChangeShapeUse,
    ) -> tuple[_RelatedSpec, dict[str, Any]]:
        _require_authority(authority)
        require_initialized_impl(
            value,
            related_type,
            "related Change Shape use",
        )
        consumer_rule = _validated_rule_surface(
            authority,
            value.consumer_rule,
            "related Change Shape consumer",
        )
        matches = tuple(
            spec for spec in related_specs if spec[0] == consumer_rule.rule_id
        )
        if len(matches) != 1:
            raise ChangeShapeCompileError(
                "related Change Shape consumer is outside the census"
            )
        spec = matches[0]
        if not same_requirement_impl(
            consumer_rule.requirement,
            related_requirement_impl(spec),
        ):
            raise ChangeShapeCompileError(
                "related Change Shape retained the wrong consumer"
            )
        consumer = adapter_validate_selection(
            authority,
            consumer_rule.selection,
        )
        _parse_related(consumer, spec)
        if type(value.provider_rules) is not tuple:
            raise TypeError(
                "related Change Shape providers must be an exact tuple"
            )
        expected_ids = _related_provider_ids(spec)
        if (
            tuple(
                item.rule_id
                for item in value.provider_rules
                if type(item) is verified_rule_contract
            )
            != expected_ids
            or len(value.provider_rules) != len(expected_ids)
        ):
            raise ChangeShapeCompileError(
                "related Change Shape provider order is invalid"
            )
        verified: list[VerifiedRuleReceipt] = []
        for provider in value.provider_rules:
            rule = _validated_rule_surface(
                authority,
                provider,
                "related Change Shape provider",
            )
            if not same_requirement_impl(
                rule.requirement,
                provider_requirement_impl(
                    provider_spec_impl(rule.rule_id, provider_specs)
                ),
            ):
                raise ChangeShapeCompileError(
                    "related Change Shape retained the wrong provider"
                )
            verified.append(rule)
        providers = tuple(verified)
        adapter_require_shared(
            authority,
            consumer,
            (consumer_rule, *providers),
        )
        canonical = _canonical_related(spec, consumer_rule, providers)
        supplied = _related_payload(value, spec)
        expected = _related_payload(canonical, spec)
        if canonical_json_impl(supplied) != canonical_json_impl(expected):
            raise ChangeShapeCompileError(
                "related Change Shape use differs from current source"
            )
        return spec, supplied

    def change_shape_consumer_requirements(
    ) -> tuple[RuleRequirement, ...]:
        return tuple(
            direct_requirement_impl(spec) for spec in direct_specs
        )

    def change_shape_provider_requirements(
    ) -> tuple[RuleRequirement, ...]:
        return tuple(
            provider_requirement_impl(spec) for spec in provider_specs
        )

    def change_shape_related_requirements(
    ) -> tuple[RuleRequirement, ...]:
        return tuple(
            related_requirement_impl(spec) for spec in related_specs
        )

    def compile_change_shape(
        authority: SourceAuthorityAdapter,
        consumer_receipt: SourceReceipt,
    ) -> CompiledChangeShape:
        consumer, consumer_rule, spec = _consumer_and_spec(
            authority,
            consumer_receipt,
        )
        provider_ids = _expected_direct_provider_ids(spec)
        providers = _resolve_providers(
            authority,
            consumer,
            consumer_rule,
            provider_ids,
        )
        result = _canonical_compiled(spec, consumer_rule, providers)
        _validate_compiled(authority, result)
        return result

    def compile_change_shape_census(
        authority: SourceAuthorityAdapter,
    ) -> tuple[CompiledChangeShape, ...]:
        _require_authority(authority)
        result: list[CompiledChangeShape] = []
        for spec in direct_specs:
            consumer_rule = adapter_validate_rule(
                authority,
                adapter_resolve_rule(
                    authority,
                    direct_requirement_impl(spec),
                ),
            )
            result.append(
                compile_change_shape(
                    authority,
                    consumer_rule.receipt,
                )
            )
        compiled = tuple(result)
        if len(compiled) != 41:
            raise AssertionError(
                "reviewed Change Shape census is incomplete"
            )
        return compiled

    def validate_compiled_change_shape(
        authority: SourceAuthorityAdapter,
        value: CompiledChangeShape,
    ) -> CompiledChangeShape:
        _validate_compiled(authority, value)
        return value

    def link_change_shape(
        authority: SourceAuthorityAdapter,
        value: CompiledChangeShape,
    ) -> LinkedChangeShape:
        _validate_compiled(authority, value)
        linked = _canonical_link(value)
        _validate_linked(authority, linked)
        return linked

    def validate_linked_change_shape(
        authority: SourceAuthorityAdapter,
        value: LinkedChangeShape,
    ) -> LinkedChangeShape:
        _validate_linked(authority, value)
        return value

    def compile_related_change_shape(
        authority: SourceAuthorityAdapter,
        consumer_receipt: SourceReceipt,
    ) -> RelatedChangeShapeUse:
        consumer, consumer_rule, spec = _related_consumer_and_spec(
            authority,
            consumer_receipt,
        )
        provider_ids = _related_provider_ids(spec)
        providers = _resolve_providers(
            authority,
            consumer,
            consumer_rule,
            provider_ids,
        )
        result = _canonical_related(spec, consumer_rule, providers)
        _validate_related(authority, result)
        return result

    def compile_related_change_shape_census(
        authority: SourceAuthorityAdapter,
    ) -> tuple[RelatedChangeShapeUse, ...]:
        _require_authority(authority)
        result: list[RelatedChangeShapeUse] = []
        for spec in related_specs:
            consumer_rule = adapter_validate_rule(
                authority,
                adapter_resolve_rule(
                    authority,
                    related_requirement_impl(spec),
                ),
            )
            result.append(
                compile_related_change_shape(
                    authority,
                    consumer_rule.receipt,
                )
            )
        compiled = tuple(result)
        if len(compiled) != 5:
            raise AssertionError(
                "reviewed related Change Shape census is incomplete"
            )
        return compiled

    def validate_related_change_shape(
        authority: SourceAuthorityAdapter,
        value: RelatedChangeShapeUse,
    ) -> RelatedChangeShapeUse:
        _validate_related(authority, value)
        return value

    def compiled_as_serialized(
        value: CompiledChangeShape,
        authority: SourceAuthorityAdapter,
    ) -> dict[str, Any]:
        _spec, payload = _validate_compiled(authority, value)
        return payload

    def linked_as_serialized(
        value: LinkedChangeShape,
        authority: SourceAuthorityAdapter,
    ) -> dict[str, Any]:
        return _validate_linked(authority, value)

    def related_as_serialized(
        value: RelatedChangeShapeUse,
        authority: SourceAuthorityAdapter,
    ) -> dict[str, Any]:
        _spec, payload = _validate_related(authority, value)
        return payload

    def validate_change_shape_link_graph(
        edges: tuple[ChangeShapeLinkEdge, ...],
    ) -> None:
        validate_edges_impl(
            edges,
            edge_type,
            maximum_links=64,
            maximum_depth=16,
        )

    return (
        change_shape_consumer_requirements,
        change_shape_provider_requirements,
        change_shape_related_requirements,
        compile_change_shape,
        compile_change_shape_census,
        validate_compiled_change_shape,
        link_change_shape,
        validate_linked_change_shape,
        compile_related_change_shape,
        compile_related_change_shape_census,
        validate_related_change_shape,
        compiled_as_serialized,
        linked_as_serialized,
        related_as_serialized,
        validate_change_shape_link_graph,
    )


(
    change_shape_consumer_requirements,
    change_shape_provider_requirements,
    change_shape_related_requirements,
    compile_change_shape,
    compile_change_shape_census,
    validate_compiled_change_shape,
    link_change_shape,
    validate_linked_change_shape,
    compile_related_change_shape,
    compile_related_change_shape_census,
    validate_related_change_shape,
    _compiled_as_serialized,
    _linked_as_serialized,
    _related_as_serialized,
    validate_change_shape_link_graph,
) = _bind_reviewed_api(
    _DIRECT_SPECS,
    _PROVIDER_SPECS,
    _RELATED_SPECS,
    _FORM_PROVIDER_IDS,
    _PROVIDER_PURPOSES,
    _RUNTIME_DEPENDENCIES,
    _DRYAD_DEPENDENCY,
    _CONCENTRATION_DEPENDENCY,
    compiled_type=CompiledChangeShape,
    linked_type=LinkedChangeShape,
    related_type=RelatedChangeShapeUse,
    form_type=ChangeShapeFormReference,
    dependency_type=ChangeShapeDependency,
    addressability_type=ChangeShapeAddressability,
    conflict_type=ChangeShapeTraitConflict,
    edge_type=ChangeShapeLinkEdge,
)

type.__setattr__(
    CompiledChangeShape,
    "as_serialized",
    _compiled_as_serialized,
)
type.__setattr__(
    LinkedChangeShape,
    "as_serialized",
    _linked_as_serialized,
)
type.__setattr__(
    RelatedChangeShapeUse,
    "as_serialized",
    _related_as_serialized,
)

for _artifact_type in (
    ChangeShapeAddressability,
    ChangeShapeDependency,
    ChangeShapeFormReference,
    ChangeShapeTraitConflict,
    ChangeShapeLinkEdge,
    CompiledChangeShape,
    LinkedChangeShape,
    RelatedChangeShapeUse,
    _NoTransfer,
):
    _seal_type(_artifact_type)
del _artifact_type


__all__ = [
    "COMPILED_CENSUS_SHA256",
    "CONSUMER_CENSUS_COUNT",
    "CONSUMER_REQUIREMENTS_SHA256",
    "CompiledChangeShape",
    "ChangeShapeAddressability",
    "ChangeShapeCompileError",
    "ChangeShapeDependency",
    "ChangeShapeFormReference",
    "ChangeShapeLinkEdge",
    "ChangeShapeLinkError",
    "ChangeShapeTraitConflict",
    "DIRECT_CENSUS_SHA256",
    "FAMILY_ID",
    "LinkedChangeShape",
    "LINKED_CENSUS_SHA256",
    "MAX_CHANGE_SHAPE_DEPTH",
    "MAX_CHANGE_SHAPE_LINKS",
    "MAX_CHANGE_SHAPE_LINK_DEPTH",
    "MAX_CHANGE_SHAPE_NODES",
    "MECHANIC_TYPE",
    "MONSTER_CORE_SOURCE_ID",
    "PLAYER_CORE_SOURCE_ID",
    "PROVIDER_REQUIREMENTS_SHA256",
    "REGISTRY_STATUS",
    "RELATED_CENSUS_COUNT",
    "RELATED_CENSUS_SHA256",
    "RELATED_OUTPUT_SHA256",
    "RELATED_REQUIREMENTS_SHA256",
    "RelatedChangeShapeUse",
    "change_shape_consumer_requirements",
    "change_shape_provider_requirements",
    "change_shape_related_requirements",
    "compile_change_shape",
    "compile_change_shape_census",
    "compile_related_change_shape",
    "compile_related_change_shape_census",
    "link_change_shape",
    "validate_change_shape_link_graph",
    "validate_compiled_change_shape",
    "validate_linked_change_shape",
    "validate_related_change_shape",
]
