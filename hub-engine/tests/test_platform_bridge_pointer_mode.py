"""平台记忆**指针模式**（2026-11-13）。

## 为什么有它

平台记忆文件是**每轮对话都加载**的输入（hermes: `agent/system_prompt.py:529`
⇒ `MEMORY.md` 全文进系统提示）⇒ 权威卡正文全是「每轮固定 token 成本」。

实测代价：hermes `MEMORY.md` 14,188 字符 / 上限 16,000 ⇒ **89% 满**，
再加 8 张卡就撞死（推后 23,041 > 16,000 ⇒ 闸直接拒绝写入）。

指针模式：平台只收「**卡名 + 一句话 + 中枢检索路径**」，正文留中枢按需检索。
⇒ 规则覆盖不丢（平台记忆里已有 GR-1「必须检索中枢」⇒ 指针是被读的**入口**）
⇒ 每轮固定成本 1,822,977 → 147,815 字符（**降 91.9%**）。

## 本文件钉死四件事

1. 默认 `full` ⇒ **行为逐字不变**（向后兼容）。
2. `pointer` 模式推的块**不含正文**，只含卡名 + 摘要 + 中枢路径。
3. 摘要来自 frontmatter `description` / 正文首个引用行 / H1（**不是**截断正文）。
4. 幂等：同一张卡推两次 ⇒ 第二次 `skipped`。

## 红绿证明

对**没有指针模式**的实现必红（推出去的仍是全文）。
"""

from __future__ import annotations

from pathlib import Path

import yaml

from tools.platform_bridge import MdSectionAdapter, _pointer_body, push


def _cfg_set(root: Path, name: str, key: str, value) -> None:
    cfg_path = root / "hub.config.yaml"
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    data.setdefault("platforms", {}).setdefault(name, {})[key] = value
    cfg_path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _card(root: Path, name: str, body: str) -> None:
    p = root / "rules" / f"{name}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        f"---\ntype: rule\ntags: [t]\nupdated: 2026-11-13\nstatus: active\nreuse_count: 0\n---\n{body}\n",
        encoding="utf-8",
    )


class TestDefaultUnchanged:
    """默认口径必须逐字不变（回归网）。"""

    def test_default_mode_is_full(self, tmp_path):
        from tools.platform_bridge import _push_mode

        root = tmp_path / "hub"
        (root / "rules").mkdir(parents=True)
        (root / "hub.config.yaml").write_text(
            yaml.safe_dump({"platforms": {"p": {}}}, allow_unicode=True), encoding="utf-8"
        )
        assert _push_mode(type("C", (), {"platforms": {"p": {}}})(), "p") == "full"

    def test_invalid_mode_raises(self, tmp_path):
        from tools.platform_bridge import _push_mode

        cfg = type("C", (), {"platforms": {"p": {"memory_push_mode": "bogus"}}})()
        try:
            _push_mode(cfg, "p")
        except ValueError:
            return
        raise AssertionError("非法 memory_push_mode 应当抛错（fail-closed）")


class TestPointerBody:
    """指针块的构造。"""

    def test_pointer_contains_no_full_body(self, tmp_path):
        """指针块**不含正文**。"""
        root = tmp_path / "hub"
        _card(root, "demo-rule", "这是一段很长的正文。" * 50)

        class C:
            path = root / "rules" / "demo-rule.md"
            body = "这是一段很长的正文。" * 50

        body = _pointer_body(C(), root)
        assert "这是一段很长的正文" * 3 not in body
        assert len(body) < 300

    def test_pointer_has_name_and_hub_path(self, tmp_path):
        """指针块含**卡名 + 中枢路径**。"""
        root = tmp_path / "hub"
        _card(root, "demo-rule", "正文")

        class C:
            path = root / "rules" / "demo-rule.md"
            body = "正文"

        body = _pointer_body(C(), root)
        assert "demo-rule" in body
        assert "rules/demo-rule.md" in body

    def test_summary_prefers_frontmatter_description(self, tmp_path):
        """摘要优先取 frontmatter `description`。"""
        root = tmp_path / "hub"
        p = root / "rules" / "demo.md"
        p.parent.mkdir(parents=True)
        p.write_text(
            "---\ntype: rule\ndescription: 这是精炼的描述\nupdated: 2026-11-13\n---\n# 标题\n> 引用行\n",
            encoding="utf-8",
        )

        class C:
            path = p
            body = "x"

        body = _pointer_body(C(), root)
        assert "这是精炼的描述" in body

    def test_summary_falls_back_to_quote_line(self, tmp_path):
        """无 description ⇒ 取正文首个引用行（中枢卡惯例 = 一句话导语）。"""
        root = tmp_path / "hub"
        p = root / "rules" / "demo.md"
        p.parent.mkdir(parents=True)
        p.write_text("---\ntype: rule\n---\n# 标题\n\n> 这是导语。\n\n正文\n", encoding="utf-8")

        class C:
            path = p
            body = "x"

        body = _pointer_body(C(), root)
        assert "这是导语" in body


class TestPointerPush:
    """指针模式的实际推送。"""

    def _setup(self, tmp_path):
        from tests.test_platform_bridge import _register_platform

        root = tmp_path / "hub"
        root.mkdir(parents=True, exist_ok=True)
        (root / "rules").mkdir(parents=True, exist_ok=True)
        (root / "hub.config.yaml").write_text(yaml.safe_dump({"platforms": {}}, allow_unicode=True), encoding="utf-8")
        mem = tmp_path / "plat"
        mem.mkdir()
        (mem / "MEMORY.md").write_text("## 已有\n旧内容\n", encoding="utf-8")
        _register_platform(root, "testplat", mem)
        return root, mem / "MEMORY.md"

    def test_pointer_push_writes_pointer_not_full(self, tmp_path):
        """指针模式推出去的是**指针**，不是正文。"""
        root, target = self._setup(tmp_path)
        long_body = "唯一标记XYZ。" * 80
        _card(root, "demo-rule", long_body)
        _cfg_set(root, "testplat", "memory_push_mode", "pointer")

        stat = push(root, "testplat", name_filter="demo-rule")
        assert stat["status"] == "ok"
        text = target.read_text(encoding="utf-8")
        assert "唯一标记XYZ" not in text, "指针模式不该把正文推下去"
        assert "demo-rule" in text

    def test_pointer_push_is_idempotent(self, tmp_path):
        """同一张卡推两次 ⇒ 第二次 skipped。"""
        root, target = self._setup(tmp_path)
        _card(root, "demo-rule", "正文内容")
        _cfg_set(root, "testplat", "memory_push_mode", "pointer")

        s1 = push(root, "testplat", name_filter="demo-rule")
        s2 = push(root, "testplat", name_filter="demo-rule")
        assert s1["added"] == 1
        assert s2["skipped"] == 1

    def test_full_mode_still_writes_full_body(self, tmp_path):
        """`full` 模式（默认）**照旧推全文**（向后兼容）。"""
        root, target = self._setup(tmp_path)
        marker = "唯一标记XYZ。"
        _card(root, "demo-rule", marker * 80)

        stat = push(root, "testplat", name_filter="demo-rule")
        assert stat["status"] == "ok"
        assert marker in target.read_text(encoding="utf-8")

    def test_pointer_saves_majority_of_chars(self, tmp_path):
        """指针体量**显著小于**全文（这是本模式的存在理由）。"""
        root, target = self._setup(tmp_path)
        body = "规则正文内容。" * 200
        _card(root, "demo-rule", body)

        _cfg_set(root, "testplat", "memory_push_mode", "pointer")
        push(root, "testplat", name_filter="demo-rule")
        ptr_size = len(target.read_text(encoding="utf-8"))

        # 换回 full 再量一次
        target.write_text("## 已有\n旧内容\n", encoding="utf-8")
        state = root / ".sync" / "state" / "pulled_testplat.json"
        if state.exists():
            state.unlink()
        _cfg_set(root, "testplat", "memory_push_mode", "full")
        push(root, "testplat", name_filter="demo-rule")
        full_size = len(target.read_text(encoding="utf-8"))

        assert ptr_size < full_size / 2, f"指针 {ptr_size} 应远小于全文 {full_size}"


class TestPointerIndexIdempotency:
    """指针**清单区**的幂等（迭代2 的核心不变量）。

    ⚠ 实测踩过的三个坑（全部会造成「推一次丢一块内容」）：
      ① span 往后找 `§` 分隔 ⇒ 吞掉清单后面的 global-rules 全文（少 2,364 字符）
      ② span 吃空行 ⇒ 吞掉 global-rules 标题行
      ③ 区间替换时新块缺尾换行 ⇒ 每次推漂移 1 字符（非幂等）
    ⇒ 本类把「重复推送不改变内容」钉死。
    """

    def _setup(self, tmp_path, tail: str = ""):
        from tests.test_platform_bridge import _register_platform

        root = tmp_path / "hub"
        root.mkdir(parents=True, exist_ok=True)
        (root / "rules").mkdir(parents=True, exist_ok=True)
        (root / "hub.config.yaml").write_text(yaml.safe_dump({"platforms": {}}, allow_unicode=True), encoding="utf-8")
        mem = tmp_path / "plat"
        mem.mkdir()
        (mem / "MEMORY.md").write_text("## 已有\n旧内容\n", encoding="utf-8")
        _register_platform(root, "testplat", mem)
        _cfg_set(root, "testplat", "memory_push_mode", "pointer")
        _card(root, "demo-rule", "正文内容" * 50)
        return root, mem / "MEMORY.md"

    def test_second_push_is_byte_identical(self, tmp_path):
        """推两次 ⇒ 文件**逐字符相同**。"""
        root, target = self._setup(tmp_path)
        push(root, "testplat", name_filter="demo-rule")
        first = target.read_text(encoding="utf-8")
        push(root, "testplat", name_filter="demo-rule")
        second = target.read_text(encoding="utf-8")
        assert first == second, "第二次推送改变了内容 ⇒ 清单区不幂等"

    def test_index_does_not_swallow_following_content(self, tmp_path):
        """⚠ 托管区**不得**吞掉它后面的内容。

        ⚠ 迭代4 起改为**托管区哨兵**方案 ⇒ 清单区被哨兵包围 ⇒ 替换边界由哨兵决定。
        ⚠ **托管区之内**的内容归中枢托管（重建时会被覆盖）⇒ 本测试在
          **end 哨兵之后**插入内容 ⇒ 那部分必须原样保留。
        """
        root, target = self._setup(tmp_path)
        push(root, "testplat", name_filter="demo-rule")  # 建托管区
        text = target.read_text(encoding="utf-8")
        marker = "\n# 其它内容标题\n\n不要丢我。\n"
        # 插到托管区**之后**（end 哨兵行之后）
        idx = text.find("<!-- hub-managed:end -->")
        assert idx > 0
        eol = text.find("\n", idx)
        new_text = text[: eol + 1] + marker + text[eol + 1 :]
        target.write_text(new_text, encoding="utf-8")
        # 更新基线（模拟受控编辑）
        from tools.platform_bridge import _read_state, _write_state, fingerprint

        st = _read_state(root, "testplat")
        st["push"] = {"hash": fingerprint(new_text), "mtime": target.stat().st_mtime_ns}
        _write_state(root, "testplat", st)

        push(root, "testplat", name_filter="demo-rule")
        after = target.read_text(encoding="utf-8")
        assert "不要丢我。" in after, "托管区替换吞掉了后面的内容 ⇒ 越界 bug"
        assert "其它内容标题" in after

    def test_index_contains_all_pushed_cards(self, tmp_path):
        """清单区包含**全部**推送集合的卡（不漏）。"""
        root, target = self._setup(tmp_path)
        _card(root, "second-rule", "另一个正文")
        push(root, "testplat")
        text = target.read_text(encoding="utf-8")
        assert "demo-rule" in text
        assert "second-rule" in text

    def test_single_card_push_keeps_whole_index(self, tmp_path):
        """⚠⚠ 推**单张**卡 ⇒ 清单区**不得**被替换成只剩那张卡。

        实测 bug（2026-11-13）：清单按「本次推送集合」重算
        ⇒ `--name xxx` 推一张就把清单清空（7,457 → 5,186，少 2,271 字符）
        ⇒ **规则清单丢失** ⇒ 平台再也看不到其它规则在哪。
        """
        root, target = self._setup(tmp_path)
        _card(root, "second-rule", "另一个正文")
        push(root, "testplat")  # 先推全量，建立完整清单
        full_text = target.read_text(encoding="utf-8")
        assert "second-rule" in full_text

        # 再单独推一张
        push(root, "testplat", name_filter="demo-rule")
        after = target.read_text(encoding="utf-8")
        assert "second-rule" in after, "推单张卡把清单里其它卡弄丢了 ⇒ 回归"
        assert "demo-rule" in after

    def test_index_reflects_full_rules_regardless_of_name_filter(self, tmp_path):
        """清单区来源 = 全量 rules/，与 `--name` 过滤无关。"""
        root, target = self._setup(tmp_path)
        _card(root, "second-rule", "另一个正文")
        push(root, "testplat", name_filter="demo-rule")
        after = target.read_text(encoding="utf-8")
        assert "second-rule" in after, "清单只含被过滤的那张 ⇒ 全量口径失效"


class TestKeepInlineWhitelist:
    """`global-rules`（GR-1~GR-4）**永远内联**。

    理由：它是**每轮都该生效**的铁律 ⇒ 指针化会削弱合规性，
    与「更好遵循规则」的目标相反。
    """

    def _setup(self, tmp_path, keep_inline: str = "global-rules"):
        from tests.test_platform_bridge import _register_platform

        root = tmp_path / "hub"
        root.mkdir(parents=True, exist_ok=True)
        (root / "rules").mkdir(parents=True, exist_ok=True)
        (root / "hub.config.yaml").write_text(yaml.safe_dump({"platforms": {}}, allow_unicode=True), encoding="utf-8")
        mem = tmp_path / "plat"
        mem.mkdir()
        (mem / "MEMORY.md").write_text("## 已有\n旧内容\n", encoding="utf-8")
        _register_platform(root, "testplat", mem)
        _cfg_set(root, "testplat", "memory_push_mode", "pointer")
        _card(root, keep_inline, "# 全局规则（GR-1 ~ GR-4）\n\n## GR-1 执行前先查记忆中枢\n\n查中枢。\n")
        _card(root, "other-rule", "其它规则正文")
        return root, mem / "MEMORY.md"

    def test_keep_inline_card_is_not_deleted(self, tmp_path):
        """白名单卡的**全文不被删**。"""
        root, target = self._setup(tmp_path)
        push(root, "testplat")
        text = target.read_text(encoding="utf-8")
        assert "全局规则（GR-1 ~ GR-4）" in text, "global-rules 全文被删了 ⇒ 铁律失去内联"
        assert "查中枢。" in text

    def test_keep_inline_card_not_in_pointer_index(self, tmp_path):
        """白名单卡**不出现在指针清单**（避免两份口径）。"""
        root, target = self._setup(tmp_path)
        push(root, "testplat")
        text = target.read_text(encoding="utf-8")
        idx = text.find("【中枢规则指针清单】")
        idx_block = text[idx:]
        assert "**global-rules**" not in idx_block, "global-rules 既内联又在清单里 ⇒ 两份口径"
        assert "**other-rule**" in idx_block, "其它卡应当出现在清单里"


class TestOldFullBlocksCleanup:
    """指针模式切换前推的**旧全文块**必须被清理。"""

    def test_old_slug_blocks_removed(self, tmp_path):
        """旧的 `## <slug>` 全文块被删（否则清单区 + 旧全文并存 ⇒ 臃肿）。"""
        from tests.test_platform_bridge import _register_platform

        root = tmp_path / "hub"
        root.mkdir(parents=True, exist_ok=True)
        (root / "rules").mkdir(parents=True, exist_ok=True)
        (root / "hub.config.yaml").write_text(yaml.safe_dump({"platforms": {}}, allow_unicode=True), encoding="utf-8")
        mem = tmp_path / "plat"
        mem.mkdir()
        # 模拟「切换指针模式前」的旧全文形态
        (mem / "MEMORY.md").write_text(
            "## 已有\n旧内容\n\n## old-rule\n这是一段很长的旧规则正文。\n重复内容。\n重复内容。\n",
            encoding="utf-8",
        )
        _register_platform(root, "testplat", mem)
        _cfg_set(root, "testplat", "memory_push_mode", "pointer")
        _card(root, "old-rule", "新正文")

        push(root, "testplat")
        text = mem / "MEMORY.md"
        out = text.read_text(encoding="utf-8")
        assert "## old-rule" not in out, "旧全文块没被清理 ⇒ 清单区与旧全文并存"
        assert "这是一段很长的旧规则正文" not in out

    def test_card_internal_subheadings_not_misread_as_blocks(self, tmp_path):
        """卡片**内部**的中文子标题不算独立块（不能被当成下一张卡的起点）。"""
        from tools.platform_bridge import _slug_block_line_ranges

        text = "## card-a\n正文\n## 关键语义\n子节正文\n## card-b\n另一张卡\n"
        hits = _slug_block_line_ranges(text, {"card-a", "card-b"})
        starts = [h[0] for h in hits]
        assert starts == [0, 4], f"卡内中文子标题被误当块边界 ⇒ {hits}"


def test_md_adapter_available():
    """守护：指针模式依赖的渲染器在位。"""
    assert hasattr(MdSectionAdapter(), "render")


class TestManagedZone:
    """**托管区哨兵**方案（迭代4）—— 边界由哨兵决定 ⇒ 天然幂等。

    ⚠ 迭代 2/3 的教训（为什么必须用哨兵而不是逐块定位）：
      · 交错结构下逐块定位互吞（workbuddy：`## global-rules` 与 `# 全局规则` 交错
        ⇒ 推 3 次体量 11,556 → 12,887 → 9,157 ⇒ 不幂等）。
      · 靠猜边界会越界吞别的内容（实测吞 2,364 字符）。
    """

    def _setup(self, tmp_path, seed: str = "## 已有\n旧内容\n"):
        from tests.test_platform_bridge import _register_platform

        root = tmp_path / "hub"
        root.mkdir(parents=True, exist_ok=True)
        (root / "rules").mkdir(parents=True, exist_ok=True)
        (root / "hub.config.yaml").write_text(yaml.safe_dump({"platforms": {}}, allow_unicode=True), encoding="utf-8")
        mem = tmp_path / "plat"
        mem.mkdir()
        (mem / "MEMORY.md").write_text(seed, encoding="utf-8")
        _register_platform(root, "testplat", mem)
        _cfg_set(root, "testplat", "memory_push_mode", "pointer")
        _card(root, "demo-rule", "正文内容")
        return root, mem / "MEMORY.md"

    def test_zone_has_sentinels(self, tmp_path):
        """托管区带**首尾哨兵** ⇒ 边界可精确定位。"""
        root, target = self._setup(tmp_path)
        push(root, "testplat")
        text = target.read_text(encoding="utf-8")
        assert "<!-- hub-managed:begin -->" in text
        assert "<!-- hub-managed:end -->" in text

    def test_zone_is_rebuilt_not_appended(self, tmp_path):
        """托管区**完全重建** ⇒ 推 3 次内容逐字符相同。"""
        root, target = self._setup(tmp_path)
        push(root, "testplat")
        a = target.read_text(encoding="utf-8")
        push(root, "testplat")
        b = target.read_text(encoding="utf-8")
        push(root, "testplat")
        c = target.read_text(encoding="utf-8")
        assert a == b == c, "托管区不是重建 ⇒ 逐次追加 ⇒ 不幂等"

    def test_content_outside_zone_survives(self, tmp_path):
        """托管区**之外**的内容必须原样保留（不被吞、不被改）。"""
        seed = "## 前置内容\n前置正文\n\n## 后置内容\n后置正文\n"
        root, target = self._setup(tmp_path, seed=seed)
        push(root, "testplat")
        text = target.read_text(encoding="utf-8")
        assert "前置正文" in text
        assert "后置正文" in text

    def test_single_card_push_keeps_whole_zone(self, tmp_path):
        """推单张卡 ⇒ 托管区**不丢**其它卡（清单仍完整）。"""
        root, target = self._setup(tmp_path)
        _card(root, "second-rule", "另一个正文")
        push(root, "testplat", name_filter="demo-rule")
        text = target.read_text(encoding="utf-8")
        assert "second-rule" in text, "推单张卡把清单里其它卡弄丢了"
