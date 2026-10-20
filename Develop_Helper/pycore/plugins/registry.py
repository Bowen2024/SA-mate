"""
用于管理和执行插件的插件注册表。
"""

from typing import Any, Optional

from pycore.core.exceptions import PluginError, PluginNotFoundError
from pycore.core.logger import get_logger
from pycore.plugins.base import BasePlugin, PluginResult


class PluginRegistry:
    """
    用于管理插件的注册表。

    提供：
    - 插件注册和发现
    - 按名称执行插件
    - 生命周期管理（setup/teardown）
    - OpenAI 函数规范生成

    用法：
        registry = PluginRegistry()

        # 注册插件
        registry.register(MyPlugin())
        registry.register_all(Plugin1(), Plugin2())

        # 执行
        result = await registry.execute("my_plugin", arg1="value")

        # 获取 LLM 规范
        specs = registry.to_specs()

        # 清理
        await registry.cleanup()
    """

    def __init__(self):
        self._plugins: dict[str, BasePlugin] = {}
        self._initialized: dict[str, bool] = {}
        self._logger = get_logger()

    def register(self, plugin: BasePlugin) -> "PluginRegistry":
        """
        注册插件。

        参数：
            plugin: 要注册的插件实例

        返回：
            自身以支持链式调用

        抛出：
            PluginError: 如果同名插件已存在
        """
        if plugin.name in self._plugins:
            raise PluginError(
                f"Plugin '{plugin.name}' already registered",
                plugin_name=plugin.name,
                operation="register",
            )
        self._plugins[plugin.name] = plugin
        self._initialized[plugin.name] = False
        self._logger.debug(f"Registered plugin: {plugin.name}")
        return self

    def register_all(self, *plugins: BasePlugin) -> "PluginRegistry":
        """注册多个插件。"""
        for plugin in plugins:
            self.register(plugin)
        return self

    def unregister(self, name: str) -> "PluginRegistry":
        """
        按名称注销插件。

        参数：
            name: 要注销的插件名称

        返回：
            自身以支持链式调用
        """
        if name in self._plugins:
            del self._plugins[name]
            del self._initialized[name]
            self._logger.debug(f"Unregistered plugin: {name}")
        return self

    def get(self, name: str) -> Optional[BasePlugin]:
        """按名称获取插件，如果未找到则返回 None。"""
        return self._plugins.get(name)

    def get_or_raise(self, name: str) -> BasePlugin:
        """按名称获取插件，如果未找到则抛出异常。"""
        plugin = self._plugins.get(name)
        if not plugin:
            raise PluginNotFoundError(name)
        return plugin

    def has(self, name: str) -> bool:
        """检查插件是否存在。"""
        return name in self._plugins

    def list_plugins(self) -> list[str]:
        """列出所有已注册的插件名称。"""
        return list(self._plugins.keys())

    def list_enabled(self) -> list[str]:
        """仅列出已启用的插件名称。"""
        return [name for name, p in self._plugins.items() if p.enabled]

    def to_specs(self, enabled_only: bool = True) -> list[dict[str, Any]]:
        """
        获取所有插件规范。

        兼容 OpenAI 函数调用格式。

        参数：
            enabled_only: 仅包含已启用的插件

        返回：
            插件规范列表
        """
        plugins = self._plugins.values()
        if enabled_only:
            plugins = [p for p in plugins if p.enabled]
        return [p.to_spec() for p in plugins]

    async def execute(
        self,
        name: str,
        **kwargs,
    ) -> PluginResult:
        """
        按名称执行插件。

        参数：
            name: 插件名称
            **kwargs: 传递给插件的参数

        返回：
            执行结果的 PluginResult
        """
        plugin = self._plugins.get(name)
        if not plugin:
            return PluginResult.fail(f"Plugin '{name}' not found")

        # 如需要则初始化
        if not self._initialized.get(name):
            try:
                await plugin.setup()
                self._initialized[name] = True
                self._logger.debug(f"Initialized plugin: {name}")
            except Exception as e:
                return PluginResult.fail(f"Plugin '{name}' setup failed: {e}")

        # 执行
        self._logger.debug(f"Executing plugin: {name}", kwargs=kwargs)
        return await plugin(**kwargs)

    async def execute_many(
        self,
        calls: list[tuple[str, dict[str, Any]]],
    ) -> list[PluginResult]:
        """
        执行多个插件。

        参数：
            calls: (plugin_name, kwargs) 元组列表

        返回：
            相同顺序的 PluginResult 列表
        """
        results = []
        for name, kwargs in calls:
            result = await self.execute(name, **kwargs)
            results.append(result)
        return results

    async def cleanup(self) -> None:
        """清理所有已初始化的插件。"""
        for name, plugin in self._plugins.items():
            if self._initialized.get(name):
                try:
                    await plugin.teardown()
                    self._initialized[name] = False
                    self._logger.debug(f"Cleaned up plugin: {name}")
                except Exception as e:
                    self._logger.error(f"Plugin cleanup failed: {name}", error=str(e))

    def __len__(self) -> int:
        return len(self._plugins)

    def __contains__(self, name: str) -> bool:
        return name in self._plugins

    def __iter__(self):
        return iter(self._plugins.values())
