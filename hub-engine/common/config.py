"""配置加载：hub.config.yaml / engine.config.yaml / provider_keys.yaml"""

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


def load_yaml(path: Path) -> dict:
    """读取 YAML，失败返回空 dict"""
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError):
        return {}


@dataclass
class HubConfig:
    """中枢根配置（hub.config.yaml 的封装）"""

    root: Path
    data: dict = field(default_factory=dict)

    @classmethod
    def load(cls, root: str | Path) -> "HubConfig":
        root = Path(root)
        return cls(root=root, data=load_yaml(root / "hub.config.yaml"))

    @property
    def platforms(self) -> dict:
        """各平台 {name: {target_file, memory_dir}}"""
        return self.data.get("platforms", {})

    @property
    def draft_dir(self) -> Path:
        return self.root / self.data.get("sync", {}).get("draft_dir", ".sync/drafts")


def _normalize_gateway(cfg: dict) -> dict:
    """嵌套 → 扁平补齐（2026-09-11）。

    `system/config.yaml` 声明为「运行时配置唯一事实源」，但它用的是**嵌套** schema
    `gateway: {url, default_model, timeout_seconds, compress}`，而引擎读的是**扁平**键
    `gateway_url / default_model / timeout / compress` —— 结果真配置从未生效，
    引擎静默回退硬编码默认（OmniRoute `127.0.0.1:20128` + 模型 `auto/offline`），
    这正是 dedup 打到 OmniRoute 并 401 的根因。

    这里做**单向补齐**：仅当扁平键缺失时由嵌套键派生，绝不覆盖显式扁平值（向后兼容）。
    """
    gw = cfg.get("gateway")
    if isinstance(gw, dict):
        derived = {
            "gateway_url": gw.get("url"),
            "default_model": gw.get("default_model"),
            "timeout": gw.get("timeout_seconds"),
            "compress": gw.get("compress"),
        }
        for flat, value in derived.items():
            if value is not None and not cfg.get(flat):
                cfg[flat] = value
    return cfg


def load_engine_config(config_path: str | Path | None = None) -> dict:
    """读取运行配置（对外入口；结果经「嵌套 → 扁平」补齐）"""
    return _normalize_gateway(_load_engine_config_raw(config_path))


def _load_engine_config_raw(config_path: str | Path | None = None) -> dict:
    """读取运行配置（V1.1 兼容 system/）。

    优先级：
    1. 显式传参 config_path
    2. 环境变量 HUB_CONFIG_PATH
    3. 中枢根 system/config.yaml（推荐）
    4. 仓库内 config/engine.config.yaml（向后兼容）
    """
    if config_path is not None:
        return load_yaml(Path(config_path))
    env_path = os.environ.get("HUB_CONFIG_PATH")
    if env_path and Path(env_path).exists():
        return load_yaml(Path(env_path))
    # 尝试中枢 system/config.yaml（统一配置入口）
    try:
        hub_root_candidate = Path(__file__).resolve().parent.parent.parent / "AgentMemoryHub"
        system_cfg = hub_root_candidate / "system" / "config.yaml"
        if system_cfg.exists():
            return load_yaml(system_cfg)
    except (OSError, FileNotFoundError):
        pass
    # 回退到旧路径
    config_path = Path(__file__).resolve().parent.parent / "config" / "engine.config.yaml"
    return load_yaml(Path(config_path))


def load_provider_keys(hub_root: str | Path) -> dict:
    """读取中枢根下的 provider_keys.yaml（Key 独立文件）"""
    return load_yaml(Path(hub_root) / "provider_keys.yaml")


# 外部项目默认位置：**全仓唯一**的盘符路径字面量（换机/换盘只改这里或用 env 覆盖）。
# 为什么允许它存在：外部项目（如 SkillHub）不在本仓内，无法从 __file__ 推导；
# 散落在 20+ 个文件里才是病，收敛到一个常量 + 可覆盖是正解。
_EXTERNAL_DEFAULTS: dict[str, tuple[str, str]] = {
    "skillhub": ("SKILLHUB_ROOT", "D:/AIwork/20260821-Fan-SkillHub"),
}


def external_path(name: str, hub_root: str | Path | None = None, *, must_exist: bool = False) -> Path | None:
    """解析仓外项目根目录：**env 优先 → `<hub>/hub.config.yaml: external_paths.<name>` → 内置默认**。

    返回 None 表示三者皆无（或 must_exist=True 且路径不存在）——调用方应当
    明确跳过并报告，而不是静默拿一个错的路径去跑子进程。
    """
    env_key, builtin = _EXTERNAL_DEFAULTS.get(name, ("", ""))

    def _ok(p: Path | None) -> Path | None:
        if p is None:
            return None
        p = Path(p).expanduser()
        if must_exist and not p.exists():
            return None
        return p

    import os

    if env_key:
        raw = os.environ.get(env_key, "").strip()
        if raw:
            return _ok(Path(raw))

    if hub_root:
        cfg_file = Path(hub_root) / "hub.config.yaml"
        try:
            ext = (load_yaml(cfg_file) or {}).get("external_paths") or {}
            if isinstance(ext, dict) and ext.get(name):
                return _ok(Path(str(ext[name])))
        except (OSError, ValueError, TypeError):
            pass  # 配置缺失/损坏 → 继续回落内置默认

    return _ok(Path(builtin)) if builtin else None
