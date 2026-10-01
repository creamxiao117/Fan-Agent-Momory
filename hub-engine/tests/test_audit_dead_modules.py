"""死代码审计工具的引用口径单测（2026-10-01）。

回归背景：本工具的「零引用」结论是**退役裁决的依据**，但它只认 `import X` /
`from X import`，不认 `from scripts.X import`——而本仓跨模块导入全部用带前缀写法
（E402 bootstrap 风格）⇒ 系统性误报「零引用」（实测漏报 `scripts/card_fields.py`，
它被 set_index_meta / proofread_index_desc / 测试三处引用）。
"""

from scripts.audit_dead_modules import ref_patterns


def _hit(stem: str, text: str) -> bool:
    return any(p.search(text) for p in ref_patterns(stem))


def test_matches_dotted_import_forms():
    """带包前缀的导入必须算「有引用」（这是本仓的通用写法）"""
    assert _hit("card_fields", "from scripts.card_fields import set_fields")
    assert _hit("card_fields", "import scripts.card_fields")
    assert _hit("hub_registry", "from tools.hub_registry import scan")
    assert _hit("hub_registry", "from hub_engine.tools.hub_registry import scan")


def test_matches_plain_import_forms():
    assert _hit("foo", "import foo")
    assert _hit("foo", "from foo import bar")
    assert _hit("foo", "python foo.py")
    assert _hit("foo", '"/path/to/foo"')
    assert _hit("foo", "python -m scripts.foo --check")


def test_does_not_match_substring_of_longer_name():
    """防误判：`foobar` 不得因 `foo` 的模式被判「有引用」"""
    assert not _hit("foo", "from scripts.foobar import x")
    assert not _hit("foo", "import foobar")
    assert not _hit("foo", "from scripts.foo_bar import y")
