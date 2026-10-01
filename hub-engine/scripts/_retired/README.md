# 退役归档区（engine 侧）

**归档 ≠ 删除**：本目录保存已被取代的代码与测试，保留完整内容与可读性，便于日后取证或恢复。
机器可读清单见同目录 `RETIRED.json`（守卫测试 `tests/test_retired_archive.py` 会校验它与磁盘一致）。

## 约定（新增归档必须遵守）

1. **每个归档件的头部必须带标签块**，至少四条：

   ```text
   # @status: retired
   # @retired_at: YYYY-MM-DD
   # @original_path: <退役前的仓库相对路径>
   # @superseded_by: <取代者；确无则写「（无）」>
   # @reason: <一句话：为什么它已无用>
   # @restore: git checkout <commit> -- <原路径>
   ```

2. **同批移动其测试**：`hub-engine/tests/_retired/`（`pytest.ini` 的 `testpaths` 只收
   `hub-engine/tests`，而 `_retired` 子目录不会被收集 —— 归档测试不会再跑，但可读）。
3. **同步 `RETIRED.json`**，否则守卫测试红。
4. **归档件不再当门禁对象**：`.ruff.toml`（`**/_retired/**`）、`tests/test_no_hardcoded_paths.py`、
   `scripts/audit_dead_modules.py` 均已排除本目录 —— 保真留档优先于强行改造。
5. **不要在这里放「活代码」**：零引用但仍在用的 CLI（如 `proofread_index_desc.py`）
   留在原位并打 `@status: manual-cli` 标签，不要混进归档区。

## 恢复方式

```bash
# 方式一：按标签里的 @restore（最省事）
git checkout <retired_from_commit> -- <original_path>
# 方式二：直接取归档件内容（历史仍在，文件可读）
git show <retired_from_commit>:<original_path> > <original_path>
```

## 本批（2026-10-01，单源/定形改造的清理）

被 `scripts/render_index.py`（渲染产物）+ `tools/hub_registry.py`（派生层）+ `scripts/set_index_meta.py`
（回写入口）取代：`slim_index` / `regen_index_desc` / `fix_index_registry` / `fix_orphans`
以及两个一次性迁移脚本 `migrate_index_fields` / `migrate_l1_tier`、一个去重复分析脚本
`analyze_experience_dupes`。逐件判据见 `RETIRED.json` 与
`docs/compose/cleanup/2026-10-01-retire-list.md`。
