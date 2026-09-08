"""配置加载：hub.config.yaml / engine.config.yaml / provider_keys.yaml"""

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


def load_yaml(path: Path) -> dict:
    """读取 YAML，失败返回空 dict"""
    try:
        with open(path, "r", encoding="utf-8") as f:
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


def load_engine_config(config_path: str | Path | None = None) -> dict:
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
        hub_root_candidate = (
            Path(__file__).resolve().parent.parent.parent / "AgentMemoryHub"
        )
        system_cfg = hub_root_candidate / "system" / "config.yaml"
        if system_cfg.exists():
            return load_yaml(system_cfg)
    except (OSError, FileNotFoundError):
        pass
    # 回退到旧路径
    config_path = (
        Path(__file__).resolve().parent.parent / "config" / "engine.config.yaml"
    )
    return load_yaml(Path(config_path))


def load_provider_keys(hub_root: str | Path) -> dict:
    """读取中枢根下的 provider_keys.yaml（Key 独立文件）"""
    return load_yaml(Path(hub_root) / "provider_keys.yaml")
