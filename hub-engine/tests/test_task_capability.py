# @version V1.0 / 2026-10-02 / pi / 任务级能力装配单测（M3/Task 21）
"""`task_capability` 单测：**装→验→卸→验** 全环 + 残留检测 + 安全约束。

回归背景（用户的原始诉求）："不常用的能力在任务初期临时安装，任务结束卸载"。
没有卸载路径，临时装必然退化为永久装——故本模块的重点不是"复制文件"，
而是 **install → verify → remove(verify)** + **残留检测** 三件套。
"""

from pathlib import Path

import yaml

from scripts.task_capability import (
    append_ledger,
    deploy_scope_of,
    install,
    ledger_rows,
    remove,
    residue,
    router_records,
    skillhub_skills,
    target_dir,
    verify,
)


def _hub(tmp_path: Path, skills: dict[str, str], scopes: dict[str, str] | None = None) -> Path:
    """造一个带 SkillHub 的中枢根：`{技能名: SKILL.md 内容}`。

    `scopes` 写进 SkillHub 的 `router/router.yaml`（**deploy_scope 的唯一源**，M2/Task 16）；
    默认把测试技能声明为 `task` —— 不声明的技能按 `always` 处理，**不允许任务级装**。
    """
    scopes = scopes or {}
    hub = tmp_path / "AgentMemoryHub"
    (hub / "system").mkdir(parents=True, exist_ok=True)
    sh = tmp_path / "SkillHub"
    records = []
    for name, body in skills.items():
        d = sh / "skills" / "shared" / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(body, encoding="utf-8")
        (d / "extra.txt").write_text("payload", encoding="utf-8")
        records.append(
            {
                "name": name,
                "slot": "shared",
                "invoke": "model",
                "trigger": [name],
                "forgot": [f"not-{name}"],
                "deploy_scope": scopes.get(name, "task"),
            }
        )
    (sh / "router").mkdir(parents=True, exist_ok=True)
    (sh / "router" / "router.yaml").write_text(
        yaml.safe_dump({"version": 1, "skills": records}, allow_unicode=True), encoding="utf-8"
    )
    (hub / "hub.config.yaml").write_text(
        yaml.safe_dump({"external_paths": {"skillhub": str(sh)}}, allow_unicode=True), encoding="utf-8"
    )
    return hub


def _mk_hubdir(tmp_path: Path) -> Path:
    """造一个只含 hub.config.yaml 的空中心（供 install/remove 写账本用）。"""
    hub = tmp_path / "AgentMemoryHub"
    hub.mkdir(parents=True, exist_ok=True)
    return hub


def test_skillhub_skills_recurses_and_finds_entries(tmp_path):
    hub = _hub(tmp_path, {"alpha": "# alpha\n", "beta": "# beta\n"})
    assert sorted(skillhub_skills(hub)) == ["alpha", "beta"]


def test_install_verify_remove_full_loop(tmp_path):
    """**全环**：装上 → 验得过 → 卸掉 → 验不过（卸载必须有"确实卸了"的证据）。"""
    hub_src = _hub(tmp_path, {"alpha": "---\nname: alpha\n---\n\n正文\n"})
    hub = _mk_hubdir(tmp_path)  # 账本写这个根
    (hub / "hub.config.yaml").write_text((hub_src / "hub.config.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    project = tmp_path / "proj"

    ok, detail = install(hub, "alpha", project)
    assert ok and "已装到" in detail
    assert (target_dir(project, "alpha") / "SKILL.md").is_file()
    assert (target_dir(project, "alpha") / "extra.txt").is_file(), "整棵树都要复制"

    ok2, d2 = verify(project, "alpha")
    assert ok2 and "SKILL.md" in d2

    ok3, d3 = remove(hub, "alpha", project)
    assert ok3 and "已卸载并验证不存在" in d3
    assert not target_dir(project, "alpha").exists()
    ok4, _ = verify(project, "alpha")
    assert ok4 is False, "卸载后 verify 必须为假（否则'卸了'是自称而非事实）"


def test_install_refuses_to_overwrite(tmp_path):
    """目标已存在必须**拒绝**（不静默覆盖用户内容），--force 才允许。"""
    hub = _hub(tmp_path, {"alpha": "# a\n"})
    project = tmp_path / "proj"
    target_dir(project, "alpha").mkdir(parents=True)
    (target_dir(project, "alpha") / "user-file.txt").write_text("user data", encoding="utf-8")

    ok, detail = install(hub, "alpha", project)
    assert not ok and "已存在" in detail
    assert (target_dir(project, "alpha") / "user-file.txt").is_file(), "拒绝时不得动用户文件"

    ok2, _ = install(hub, "alpha", project, force=True)
    assert ok2 and not (target_dir(project, "alpha") / "user-file.txt").exists()


def test_install_unknown_skill_is_refused(tmp_path):
    """未知技能名必须拒绝（**不猜路径** —— 这也是路径穿越防线）。"""
    hub = _hub(tmp_path, {"alpha": "# a\n"})
    ok, detail = install(hub, "../../etc", tmp_path / "proj")
    assert not ok and "没有技能" in detail


def test_ledger_is_append_only_and_records_both_actions(tmp_path):
    hub = _mk_hubdir(tmp_path)
    append_ledger(hub, "install", "x", "/p", ok=True)
    append_ledger(hub, "remove", "x", "/p", ok=True)
    rows = ledger_rows(hub)
    assert [r["action"] for r in rows] == ["install", "remove"]
    assert all(r["deploy_scope"] == "task" for r in rows), "账本必须标明这是 task scope"


def test_residue_detects_unsettled_task_installs(tmp_path):
    """**残留检测**：装了但未卸且超期 ⇒ 报出（临时装→永久装退化的唯一防线）。"""
    hub = _hub(tmp_path, {"alpha": "# a\n"})
    project = tmp_path / "proj"
    install(hub, "alpha", project)

    # days=0 ⇒ 任何未结算的 install 都算残留
    res = residue(hub, days=0)
    assert [r["skill"] for r in res] == ["alpha"]

    remove(hub, "alpha", project)
    assert residue(hub, days=0) == [], "卸载后不得再报残留"


def test_install_refuses_always_scope(tmp_path):
    """M2/Task 16 门槛：`deploy_scope=always`（常驻）的能力**拒绝任务级装**。

    常驻的本就装在客户端——再往项目里装一份是重复部署，
    会把「临时装」变成「到处都有一份」，正是本模块要防的退化。
    """
    hub = _hub(tmp_path, {"resident": "# r\n"}, scopes={"resident": "always"})
    project = tmp_path / "proj"
    ok, detail = install(hub, "resident", project)
    assert not ok and "always" in detail and "拒绝" in detail
    assert not target_dir(project, "resident").exists()
    # 确实需要时可用 --force 越过
    ok2, _ = install(hub, "resident", project, force=True)
    assert ok2


def test_install_allows_declared_task_scope(tmp_path):
    """声明 `deploy_scope: task` 或 `on-demand` 的能力可以装（**声明是装的前提**）。"""
    hub = _hub(tmp_path, {"t1": "# t\n", "o1": "# o\n"}, scopes={"t1": "task", "o1": "on-demand"})
    project = tmp_path / "proj"
    assert install(hub, "t1", project)[0] is True
    assert install(hub, "o1", project)[0] is True


def test_no_router_records_means_always(tmp_path):
    """读不到 SkillHub 路由记录时按 `always` 处理（**保守**：宁可不许临时装，也不许静默常驻）。"""
    hub = _hub(tmp_path, {"alpha": "# a\n"})
    (hub / "hub.config.yaml").write_text(
        yaml.safe_dump({"external_paths": {"skillhub": str(tmp_path / "nope")}}, allow_unicode=True),
        encoding="utf-8",
    )
    assert deploy_scope_of(hub, "alpha") == "always"
    assert router_records(hub) == {}
