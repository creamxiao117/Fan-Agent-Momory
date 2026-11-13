# @version V1.0 / 2026-11-13 / 逐平台软目标线 + 月度体检的回归测试
"""逐平台软目标线（`per_platform_target`）与月度体检的行为契约。

## 为什么需要（用户裁定 2026-11-13）

> 「这个软目标……不应该是一个规定死的数值，对每个平台来说应该都是不一样的。
> ……可以每个月适当进行一次检查，在不改变它原本语义的情况下，尽量减少这个数值的大小，
> 把它优化在一个合理的范围内，不让它过度膨胀。」

原实现用**全平台统一常量** `per_session_target: 1500` ⇒
workbuddy（3150）与 mavis（21）拿同一把尺子 ⇒ 常年超标 ⇒ 噪音掩盖真问题。

本文件钉死三条：
1. **逐平台目标线生效**：各平台用各的目标线，不再用全局常量。
2. **语义不变**：超软目标**仍然只报不拦**（退出码不受影响）。
3. **月度体检的核心行为**：只降不升 + 膨胀检测 + 质量闸（在用能力受保护）。

## 红绿证明

对**旧实现**（只有 `per_session_target`、无 `per_platform_target`）必红；
对**新实现**全绿。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from scripts.capability_reconcile import budgets, target_for

_HUB_ENGINE = Path(__file__).resolve().parents[1]


def _write_config(root: Path, cap: dict) -> None:
    """写一份最小 hub.config.yaml（只含 capability_budget 需要的段）。"""
    (root / "hub.config.yaml").write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "platforms_global": {"capability_budget": cap},
                "platforms": {},
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )


class TestPerPlatformTarget:
    """逐平台目标线。"""

    def test_budgets_exposes_per_platform_target(self, tmp_path: Path) -> None:
        """`budgets()` 必须读出 `per_platform_target`。"""
        _write_config(
            tmp_path,
            {
                "per_session_target": 1500,
                "per_platform_target": {"workbuddy": 3150, "mavis": 21},
                "per_platform_ratchet": {"workbuddy": 3264, "mavis": 21},
            },
        )
        b = budgets(tmp_path)
        assert b["per_platform_target"] == {"workbuddy": 3150, "mavis": 21}

    def test_target_for_prefers_per_platform(self, tmp_path: Path) -> None:
        """逐平台目标线**优先于**全局回退值。"""
        b = {"per_session_target": 1500, "per_platform_target": {"workbuddy": 3150}}
        assert target_for("workbuddy", b) == 3150

    def test_target_for_falls_back_to_global(self, tmp_path: Path) -> None:
        """未登记的平台回落到全局默认值（老配置兼容）。"""
        b = {"per_session_target": 1500, "per_platform_target": {"workbuddy": 3150}}
        assert target_for("code", b) == 1500

    def test_no_global_fallback_when_per_platform_present(self, tmp_path: Path) -> None:
        """⚠️ 核心口径：**没登记目标线的平台不该被全局常量误判**。

        这是「不用一把尺子量所有平台」的关键 —— 若某平台没登记目标线，
        它的目标线就是它自己的实测基线（= 不报超目标），而不是全局 1500。
        """
        b = {"per_session_target": 0, "per_platform_target": {"workbuddy": 3150}}
        assert target_for("code", b) == 0  # 0 = 不设目标线 ⇒ 不报超目标


class TestSoftTargetStillDoesNotBlock:
    """语义不变：软目标**只报不拦**。"""

    def test_over_target_not_in_exit_code_logic(self) -> None:
        """源码级断言：`main()` 的退出码判定**不含** over_target。

        这条守住「软目标永远不拦提交」—— 拿它当门禁会在第一天就红 ⇒
        训练出 --no-verify ⇒ 门禁彻底失效。

        ⚠️ 判定时要**剥离注释**：`return 0  # over_target 是**软目标**…`
        这行注释里提到 over_target 是**故意的显式声明**，不是判定参与。
        """
        src = (_HUB_ENGINE / "scripts" / "capability_reconcile.py").read_text(encoding="utf-8")
        main_src = src.split("def main(")[-1]
        for raw in main_src.splitlines():
            # 剥离行内注释与整行注释
            code = raw.split("#", 1)[0].strip()
            if not code.startswith("return "):
                continue
            if "over_target" in code:
                pytest.fail(f"main() 的退出码分支里出现了 over_target（软目标必须只报不拦）：{code}")
        assert "over_target 是**软目标**" in src, "缺少「软目标只报不拦」的显式声明"


class TestMonthlyReview:
    """月度体检：只降不升 + 膨胀检测 + 质量闸。

    ⚠️ 2026-11-13：体检逻辑**并入** `capability_reconcile`（`--monthly` 子命令），
       不另起脚本 —— 否则模块数 114→115 会撞 C8④ 棘轮（只许不增）。
    """

    def _module(self):
        from scripts import capability_reconcile as m

        return m

    def test_detects_bloat_against_prev_baseline(self, tmp_path: Path) -> None:
        """造上月基线（低于本月）⇒ 必须判出膨胀。"""
        m = self._module()
        # 造留痕
        state = tmp_path / ".sync" / "state"
        state.mkdir(parents=True, exist_ok=True)
        (state / "capability_budget_review-2026-01.json").write_text(
            json.dumps(
                {
                    "month": "2026-01",
                    "platforms": {"code": {"current_tokens": 100}},
                }
            ),
            encoding="utf-8",
        )
        # 读基线应能取到值
        prev = m._monthly_state_dir(tmp_path) / "capability_budget_review-2026-01.json"
        assert prev.is_file()
        data = json.loads(prev.read_text(encoding="utf-8"))
        assert data["platforms"]["code"]["current_tokens"] == 100

    def test_suggested_target_never_exceeds_current(self, tmp_path: Path) -> None:
        """建议目标线 **≤ 实测**（只降不升）。

        断言落在**被测项**上：直接调 `monthly_review()`，而不是复述公式
        （复述公式 = 自己验自己，测不出实现漂移）。
        """
        m = self._module()
        # 造一份上月基线（低于本月 ⇒ 本月算「膨胀」）
        state = tmp_path / ".sync" / "state"
        state.mkdir(parents=True, exist_ok=True)
        (state / "capability_budget_review-2026-01.json").write_text(
            json.dumps({"month": "2026-01", "platforms": {}}), encoding="utf-8"
        )

        # 造一个假中枢：hub.config.yaml（含**平台元数据**——discovery_cost 按平台遍历）
        skills_dir = tmp_path / "skills"
        (skills_dir / "s1").mkdir(parents=True)
        (skills_dir / "s1" / "SKILL.md").write_text(
            "---\nname: s1\ndescription: " + ("x" * 400) + "\n---\n", encoding="utf-8"
        )
        (tmp_path / "hub.config.yaml").write_text(
            yaml.safe_dump(
                {
                    "version": 1,
                    "platforms_global": {
                        "capability_budget": {
                            "per_platform_ratchet": {"code": 9999},
                            "per_platform_target": {"code": 500},
                        }
                    },
                    "platforms": {
                        "code": {
                            "skills_dir": str(skills_dir),
                            "mcp_config_path": "",
                        }
                    },
                },
                allow_unicode=True,
            ),
            encoding="utf-8",
        )

        rep = m.monthly_review(tmp_path)
        p = rep["platforms"]["code"]
        assert p["current_tokens"] > 0
        # 建议目标线**永远 ≤ 实测**（只降不升）
        assert p["suggested_target"] <= p["current_tokens"]

    def test_quality_gate_protects_in_use_skills(self, tmp_path: Path) -> None:
        """质量闸：在用能力（已登记）标记为**不可自动降级**。

        信号源 = SkillHub `router/router.yaml` 登记名 + 实现目录名。
        """
        m = self._module()
        # 造一个假 skillhub
        sh = tmp_path / "skillhub"
        (sh / "router").mkdir(parents=True)
        (sh / "skills" / "my-skill").mkdir(parents=True)
        (sh / "skills" / "my-skill" / "SKILL.md").write_text("x", encoding="utf-8")
        (sh / "router" / "router.yaml").write_text(
            yaml.safe_dump({"skills": [{"name": "my-skill"}]}, allow_unicode=True),
            encoding="utf-8",
        )

        # monkeypatch external_path 指向假 skillhub
        import common.config as cfg

        orig = cfg.external_path
        try:
            cfg.external_path = lambda name, root: str(sh) if name == "skillhub" else orig(name, root)
            used = m._monthly_used_skills(tmp_path)
        finally:
            cfg.external_path = orig

        assert "my-skill" in used, "质量闸没认出已登记的技能"

    def test_review_exit_code_always_zero(self, tmp_path: Path) -> None:
        """体检入口**永远 exit 0**（只建议 ⇒ 不拦任何东西）。"""
        m = self._module()
        # 缺配置时也不该抛非 0
        rc = m.main(["--monthly", "--root", str(tmp_path)])
        assert rc == 0

    def test_same_month_bloat_detected_via_last_snapshot(self, tmp_path: Path) -> None:
        """⚠️ 同月内膨胀检测（2026-11-13 补的真实漏洞）。

        原实现只比对**上月**留痕 ⇒ 同月内连续跑多次时，膨胀永远看不出来
        （例：code 上月=1312，本月内加技能→1400，比对 1312 仍判「未膨胀」）。

        修法：另写 `capability_budget_review-last.json`（上次运行快照）⇒ 逐次比对。

        本测试用**假中枢**验证：先写一份 last 基线（比实测低）⇒ 必须判膨胀。
        """
        m = self._module()
        skills_dir = tmp_path / "skills"
        (skills_dir / "s1").mkdir(parents=True)
        (skills_dir / "s1" / "SKILL.md").write_text(
            "---\nname: s1\ndescription: " + ("x" * 800) + "\n---\n", encoding="utf-8"
        )
        (tmp_path / "hub.config.yaml").write_text(
            yaml.safe_dump(
                {
                    "version": 1,
                    "platforms_global": {"capability_budget": {"per_platform_ratchet": {"code": 99999}}},
                    "platforms": {"code": {"skills_dir": str(skills_dir), "mcp_config_path": ""}},
                },
                allow_unicode=True,
            ),
            encoding="utf-8",
        )
        # 造「上次运行」基线（远低于当前实测 ⇒ 应判膨胀）
        state = tmp_path / ".sync" / "state"
        state.mkdir(parents=True, exist_ok=True)
        (state / "capability_budget_review-last.json").write_text(
            json.dumps({"month": "2026-11", "platforms": {"code": {"current_tokens": 10}}}),
            encoding="utf-8",
        )

        rep = m.monthly_review(tmp_path)
        p = rep["platforms"]["code"]
        assert p["base_label"] == "上次运行", f"未优先用『上次运行』基线：{p['base_label']}"
        assert p["bloat"] is True, "同月内膨胀没被检出"
        assert p["delta"] > 0
        # 建议目标线仍只降不升（≤ 基线）
        assert p["suggested_target"] <= p["current_tokens"]

    def test_first_run_has_no_baseline(self, tmp_path: Path) -> None:
        """首期（既无上月、也无上次运行）⇒ 应标 `has_prev=False` 且 `has_last=False`。"""
        m = self._module()
        skills_dir = tmp_path / "skills"
        (skills_dir / "s1").mkdir(parents=True)
        (skills_dir / "s1" / "SKILL.md").write_text("---\nname: s1\ndescription: x\n---\n", encoding="utf-8")
        (tmp_path / "hub.config.yaml").write_text(
            yaml.safe_dump(
                {
                    "version": 1,
                    "platforms_global": {"capability_budget": {}},
                    "platforms": {"code": {"skills_dir": str(skills_dir), "mcp_config_path": ""}},
                },
                allow_unicode=True,
            ),
            encoding="utf-8",
        )
        rep = m.monthly_review(tmp_path)
        assert rep["has_prev"] is False
        assert rep.get("has_last") is False
        # 渲染不应误报「首期」以外的矛盾
        assert "无基线" in m.render_monthly(rep)


class TestBiweeklyIdleDemotion:
    """两周窗口 + 闲置自动降级（用户裁定 2026-11-13）。

    用户原话：「月度调整改成两周调整，在两周之内没有使用的限制能力，
    就让平台不再默认加载它们。」

    ⇒ 落地：`deploy_scope: always → on-demand`（= 不再默认加载，用到时按需装）。
    """

    def _module(self):
        from scripts import capability_reconcile as m

        return m

    def _make_hub(self, tmp_path: Path, *, router_skills: list[dict]) -> Path:
        """造一个假中枢 + 假 SkillHub（含 router.yaml）。"""
        skills_dir = tmp_path / "skills"
        (skills_dir / "s1").mkdir(parents=True)
        (skills_dir / "s1" / "SKILL.md").write_text(
            "---\nname: s1\ndescription: " + ("x" * 400) + "\n---\n", encoding="utf-8"
        )
        sh = tmp_path / "skillhub"
        (sh / "router").mkdir(parents=True)
        (sh / "skills").mkdir(parents=True)
        import yaml

        (sh / "router" / "router.yaml").write_text(
            yaml.safe_dump({"version": 1, "skills": router_skills}, allow_unicode=True),
            encoding="utf-8",
        )
        (tmp_path / "hub.config.yaml").write_text(
            yaml.safe_dump(
                {
                    "version": 1,
                    "external_paths": {"skillhub": str(sh)},
                    "platforms_global": {"capability_budget": {}},
                    "platforms": {"code": {"skills_dir": str(skills_dir), "mcp_config_path": ""}},
                },
                allow_unicode=True,
            ),
            encoding="utf-8",
        )
        return sh

    def test_idle_always_skill_is_demoted(self, tmp_path: Path) -> None:
        """常驻(always) + 两周内未使用 ⇒ 降级为 on-demand。"""
        m = self._module()
        self._make_hub(tmp_path, router_skills=[{"name": "idle-skill", "deploy_scope": "always"}])

        res = m._apply_scope_demotion(tmp_path, ["idle-skill"])
        assert res["error"] is None
        assert res["changed"] == ["idle-skill"]

        import yaml

        router = yaml.safe_load((tmp_path / "skillhub" / "router" / "router.yaml").read_text(encoding="utf-8"))
        got = router["skills"][0]["deploy_scope"]
        assert got == "on-demand", f"降级未生效：{got}"

    def test_demotion_preserves_other_fields(self, tmp_path: Path) -> None:
        """降级**只改 deploy_scope 一处**，其余字段（trigger/forgot/description）必须原样保留。

        守门点：用 yaml.safe_dump 回写会重排整个文件、丢注释 ⇒ 必须行级替换。
        """
        m = self._module()
        sh = self._make_hub(
            tmp_path,
            router_skills=[
                {
                    "name": "idle-skill",
                    "deploy_scope": "always",
                    "trigger": ["用我"],
                    "forgot": ["不用我"],
                    "description_model": "保留我",
                }
            ],
        )
        m._apply_scope_demotion(tmp_path, ["idle-skill"])

        import yaml

        router = yaml.safe_load((sh / "router" / "router.yaml").read_text(encoding="utf-8"))
        row = router["skills"][0]
        assert row["trigger"] == ["用我"]
        assert row["forgot"] == ["不用我"]
        assert row["description_model"] == "保留我"
        assert row["deploy_scope"] == "on-demand"

    def test_evidence_gap_blocks_auto_demotion(self, tmp_path: Path) -> None:
        """⚠️ **证据不足 ≠ 未使用**（fail-closed）。

        若某平台**没有使用证据台账** ⇒ 该平台的「无记录」不能判定为闲置
        ⇒ 候选进 `blocked`（待人工确认），**不进** `idle`（可自动降级）。
        """
        m = self._module()
        self._make_hub(tmp_path, router_skills=[{"name": "idle-skill", "deploy_scope": "always"}])

        usage = {
            "used": set(),
            "observed_platforms": ["pi"],
            "uncovered_platforms": ["hermes", "code"],  # ⇒ 有证据缺口
        }
        info = m._find_idle_always_skills(tmp_path, usage, set())
        assert info["idle"] == [], "有证据缺口时不该产出可自动降级的清单"
        assert info["blocked"], "候选应进 blocked 待人工确认"
        assert "hermes" in info["evidence_gap_platforms"]

    def test_no_evidence_gap_allows_auto_demotion(self, tmp_path: Path) -> None:
        """无证据缺口 ⇒ 两周未用的常驻能力**可**自动降级。"""
        m = self._module()
        self._make_hub(
            tmp_path,
            router_skills=[
                {"name": "idle-skill", "deploy_scope": "always"},
                {"name": "busy-skill", "deploy_scope": "always"},
                {"name": "on-demand-skill", "deploy_scope": "on-demand"},
            ],
        )
        usage = {
            "used": {"busy-skill"},
            "observed_platforms": ["pi", "hermes", "code"],
            "uncovered_platforms": [],
        }
        info = m._find_idle_always_skills(tmp_path, usage, set())
        assert info["idle"] == ["idle-skill"], info
        assert "busy-skill" not in info["idle"]
        assert "on-demand-skill" not in info["idle"], "已是 on-demand 的不该再判闲置"

    def test_card_names_not_treated_as_skill_usage(self, tmp_path: Path) -> None:
        """⚠️ **命名空间混用 ⇒ 判定失效**（真缺陷）。

        检索日志的 `hit_paths` 是**卡片名**（`experience/xxx.md`），
        不是能力名 ⇒ 把它当「能力用过」会让真闲置能力被误判为活跃。

        本测试：只有卡片命中、能力事件为空 ⇒ 能力**不得**被算作用过。
        """
        m = self._module()
        state = tmp_path / ".sync" / "state"
        state.mkdir(parents=True)
        (state / "capability_events.jsonl").write_text("", encoding="utf-8")
        (state / "query.log-2026-11-12.jsonl").write_text(
            json.dumps(
                {
                    "ts": "2026-11-12T08:00:00+08:00",
                    "platform": "pi",
                    "hit_paths": ["experience/some-card.md"],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        # 卡片名与能力名**不同** ⇒ 不该进 used
        usage = m._usage_evidence_window(tmp_path, days=14)
        assert "some-card" not in usage["used"], "卡片名被当成了能力使用（命名空间混用）"

    def test_window_is_fourteen_days(self, tmp_path: Path) -> None:
        """窗口 = 14 天（用户裁定：月度改两周）。"""
        m = self._module()
        state = tmp_path / ".sync" / "state"
        state.mkdir(parents=True)
        (state / "capability_events.jsonl").write_text(
            json.dumps(
                {
                    "ts": "2026-11-12T08:00:00+08:00",
                    "platform": "pi",
                    "name": "recent-skill",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        usage = m._usage_evidence_window(tmp_path, days=14)
        assert usage["window_days"] == 14
        assert "recent-skill" in usage["used"]

    def test_monthly_is_subcommand_not_new_module(self) -> None:
        """月度体检**不是新模块** —— 它是 `capability_reconcile` 的子命令。

        守住 C8④「模块数棘轮不增长」：若有人把它拆回独立脚本，
        模块数会 114→115 ⇒ inventory 门禁打红。
        """
        src = (_HUB_ENGINE / "scripts" / "capability_reconcile.py").read_text(encoding="utf-8")
        assert "def monthly_review(" in src, "月度体检函数不在 capability_reconcile 内"
        assert "def _monthly_main(" in src, "月度体检 CLI 入口不在 capability_reconcile 内"
        assert not (_HUB_ENGINE / "scripts" / "capability_budget_review.py").exists(), (
            "月度体检被拆成独立脚本了 ⇒ 模块数会超棘轮 114（C8④）"
        )
