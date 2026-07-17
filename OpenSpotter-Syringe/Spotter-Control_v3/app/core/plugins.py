"""Plugin contracts and deterministic discovery for pattern generators.

The registry deliberately has no dependency on Tk or application state. Built-in
plugins and third-party entry points therefore share the same validation and
duplicate-detection rules.
"""

import importlib
import pkgutil
import re
from dataclasses import dataclass
from importlib import metadata as importlib_metadata
from threading import RLock
from types import MappingProxyType, ModuleType
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    Iterator,
    Mapping,
    Optional,
    Protocol,
    Sequence,
    Set,
    Tuple,
    runtime_checkable,
)


API_VERSION = 1
"""Version of the core-to-pattern-plugin contract."""

ENTRY_POINT_GROUP = "openspotter.patterns"
"""Entry-point group used by optional, installed pattern plugins."""

_PLUGIN_ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")


class PluginError(RuntimeError):
    """Base class for plugin registry failures."""


class PluginManifestError(PluginError, ValueError):
    """Raised when a plugin manifest or implementation is invalid."""


class PluginCompatibilityError(PluginManifestError):
    """Raised when a plugin targets a different core API version."""


class DuplicatePluginError(PluginError):
    """Raised when two sources attempt to register the same plugin ID."""


class PluginLoadError(PluginError):
    """Raised when importing or constructing a plugin fails."""

    def __init__(self, source: str, message: str):
        self.source = source
        super().__init__("{}: {}".format(source, message))


@dataclass(frozen=True)
class PluginManifest:
    """Metadata required for every pattern plugin.

    ``id`` is a stable machine-readable identifier. ``version`` describes the
    plugin release, while ``api_version`` declares the core contract it uses.
    """

    id: str
    display_name: str
    version: str
    api_version: int = API_VERSION
    description: str = ""
    capabilities: Tuple[str, ...] = ()
    dependencies: Tuple[str, ...] = ()

    @property
    def plugin_id(self) -> str:
        """Descriptive alias for callers that avoid the built-in name ``id``."""

        return self.id


@runtime_checkable
class PatternPlugin(Protocol):
    """Minimum runtime contract for a numeric pattern planner."""

    manifest: PluginManifest
    name: str

    def plan(self, context: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
        """Return numeric planning records for the supplied context."""


ErrorHandler = Callable[[PluginError], None]


def validate_manifest(manifest: PluginManifest) -> None:
    """Validate manifest structure and compatibility with this core."""

    if not isinstance(manifest, PluginManifest):
        raise PluginManifestError(
            "plugin.manifest must be a PluginManifest instance"
        )
    if not isinstance(manifest.id, str) or not _PLUGIN_ID_PATTERN.fullmatch(
        manifest.id
    ):
        raise PluginManifestError(
            "plugin ID must start with a lowercase letter and contain only "
            "lowercase letters, digits, '.', '_' or '-'"
        )
    if not isinstance(manifest.display_name, str) or not manifest.display_name.strip():
        raise PluginManifestError("plugin display_name must be a non-empty string")
    if not isinstance(manifest.version, str) or not manifest.version.strip():
        raise PluginManifestError("plugin version must be a non-empty string")
    if not isinstance(manifest.api_version, int) or isinstance(
        manifest.api_version, bool
    ):
        raise PluginManifestError("plugin api_version must be an integer")
    if manifest.api_version != API_VERSION:
        raise PluginCompatibilityError(
            "plugin {!r} targets API version {}; this core supports {}".format(
                manifest.id,
                manifest.api_version,
                API_VERSION,
            )
        )
    if not isinstance(manifest.description, str):
        raise PluginManifestError("plugin description must be a string")
    _validate_string_tuple("capabilities", manifest.capabilities)
    _validate_string_tuple("dependencies", manifest.dependencies)


def _validate_string_tuple(field_name: str, values: Tuple[str, ...]) -> None:
    if isinstance(values, str) or not isinstance(values, (tuple, list)):
        raise PluginManifestError(
            "plugin {} must be a tuple or list of strings".format(field_name)
        )
    normalized = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise PluginManifestError(
                "plugin {} entries must be non-empty strings".format(field_name)
            )
        normalized.append(value.strip())
    if len(normalized) != len(set(normalized)):
        raise PluginManifestError(
            "plugin {} must not contain duplicates".format(field_name)
        )


def validate_plugin(plugin: object) -> PluginManifest:
    """Validate an implementation and return its manifest."""

    manifest = getattr(plugin, "manifest", None)
    validate_manifest(manifest)

    planner = getattr(plugin, "plan", None)
    if not callable(planner):
        raise PluginManifestError(
            "plugin {!r} must provide a callable plan(context) method".format(
                manifest.id
            )
        )

    legacy_name = getattr(plugin, "name", None)
    if legacy_name is not None and legacy_name != manifest.id:
        raise PluginManifestError(
            "plugin name {!r} does not match manifest ID {!r}".format(
                legacy_name,
                manifest.id,
            )
        )
    return manifest


class PluginRegistry:
    """Validated registry with deterministic, idempotent discovery."""

    def __init__(self) -> None:
        self._plugins: Dict[str, object] = {}
        self._plugin_sources: Dict[str, str] = {}
        self._loaded_sources: Set[str] = set()
        self._lock = RLock()

    def register(self, plugin: object, source: str = "manual") -> object:
        """Validate and register one plugin.

        Manual duplicate registration is always an error. Discovery remains
        idempotent by remembering each successfully loaded source.
        """

        manifest = validate_plugin(plugin)
        normalized_source = str(source).strip() or "manual"
        with self._lock:
            previous_source = self._plugin_sources.get(manifest.id)
            if previous_source is not None:
                raise DuplicatePluginError(
                    "plugin {!r} from {} conflicts with {}".format(
                        manifest.id,
                        normalized_source,
                        previous_source,
                    )
                )
            self._plugins[manifest.id] = plugin
            self._plugin_sources[manifest.id] = normalized_source
        return plugin

    def get(self, plugin_id: str) -> Optional[object]:
        """Return a plugin, or ``None`` when the ID is not registered."""

        with self._lock:
            return self._plugins.get(plugin_id)

    def require(self, plugin_id: str) -> object:
        """Return a plugin or raise a descriptive ``KeyError``."""

        plugin = self.get(plugin_id)
        if plugin is None:
            raise KeyError("No pattern plugin is registered as {!r}".format(plugin_id))
        return plugin

    @property
    def plugins(self) -> Mapping[str, object]:
        """Read-only snapshot keyed in deterministic registration order."""

        with self._lock:
            return MappingProxyType(dict(self._plugins))

    def ids(self) -> Tuple[str, ...]:
        with self._lock:
            return tuple(self._plugins)

    def values(self) -> Tuple[object, ...]:
        with self._lock:
            return tuple(self._plugins.values())

    def items(self) -> Tuple[Tuple[str, object], ...]:
        with self._lock:
            return tuple(self._plugins.items())

    def __contains__(self, plugin_id: object) -> bool:
        with self._lock:
            return plugin_id in self._plugins

    def __len__(self) -> int:
        with self._lock:
            return len(self._plugins)

    def __iter__(self) -> Iterator[str]:
        return iter(self.ids())

    def clear(self) -> None:
        """Remove plugins and discovery history, primarily for isolated hosts/tests."""

        with self._lock:
            self._plugins.clear()
            self._plugin_sources.clear()
            self._loaded_sources.clear()

    def discover_builtins(
        self,
        package_name: str,
        on_error: Optional[ErrorHandler] = None,
    ) -> Tuple[str, ...]:
        """Discover package modules alphabetically and load each source once."""

        try:
            package = importlib.import_module(package_name)
        except Exception as exc:
            raise PluginLoadError(
                "package {}".format(package_name),
                "could not import package: {}".format(exc),
            ) from exc

        package_paths = getattr(package, "__path__", None)
        if package_paths is None:
            raise PluginLoadError(
                "package {}".format(package_name),
                "built-in plugin location is not a package",
            )

        module_names = sorted(
            module_info.name
            for module_info in pkgutil.iter_modules(package_paths)
            if not module_info.name.startswith("_")
        )
        loaded_ids = []
        for module_name in module_names:
            full_name = "{}.{}".format(package_name, module_name)
            source_key = "builtin:{}".format(full_name)
            plugin_id = self._load_source_once(
                source_key,
                lambda full_name=full_name: self._load_builtin_module(full_name),
                on_error,
            )
            if plugin_id is not None:
                loaded_ids.append(plugin_id)
        return tuple(loaded_ids)

    def load_entry_points(
        self,
        group: str = ENTRY_POINT_GROUP,
        entry_points: Optional[Iterable[object]] = None,
        on_error: Optional[ErrorHandler] = None,
    ) -> Tuple[str, ...]:
        """Load installed plugins from an entry-point group.

        ``entry_points`` is injectable for embedding hosts and tests. When it is
        omitted, both the Python 3.8 mapping API and newer ``select`` API are
        supported.
        """

        candidates = self._entry_points_for_group(group, entry_points)
        candidates.sort(key=self._entry_point_sort_key)

        loaded_ids = []
        for entry_point in candidates:
            name = str(getattr(entry_point, "name", "")).strip()
            if not name:
                error = PluginLoadError(
                    "entry point {}".format(group),
                    "entry point is missing a name",
                )
                if on_error is None:
                    raise error
                on_error(error)
                continue

            value = str(getattr(entry_point, "value", "")).strip()
            distribution = getattr(entry_point, "dist", None)
            distribution_name = str(
                getattr(distribution, "name", "") or ""
            ).strip()
            source_key = "entry-point:{}:{}:{}:{}".format(
                group,
                distribution_name,
                name,
                value,
            )
            display_source = "entry point {}:{}".format(group, name)
            plugin_id = self._load_source_once(
                source_key,
                lambda entry_point=entry_point, display_source=display_source: (
                    self._load_entry_point(entry_point, display_source)
                ),
                on_error,
            )
            if plugin_id is not None:
                loaded_ids.append(plugin_id)
        return tuple(loaded_ids)

    def _load_source_once(
        self,
        source_key: str,
        loader: Callable[[], object],
        on_error: Optional[ErrorHandler],
    ) -> Optional[str]:
        with self._lock:
            if source_key in self._loaded_sources:
                return None
            try:
                plugin = loader()
                manifest = validate_plugin(plugin)
                self.register(plugin, source=source_key)
            except PluginError as exc:
                if on_error is None:
                    raise
                on_error(exc)
                return None
            self._loaded_sources.add(source_key)
            return manifest.id

    @staticmethod
    def _load_builtin_module(full_name: str) -> object:
        try:
            module = importlib.import_module(full_name)
        except Exception as exc:
            raise PluginLoadError(
                "module {}".format(full_name),
                "import failed: {}".format(exc),
            ) from exc

        factory = getattr(module, "register", None)
        if not callable(factory):
            raise PluginLoadError(
                "module {}".format(full_name),
                "must expose a callable register() factory",
            )
        try:
            return factory()
        except Exception as exc:
            raise PluginLoadError(
                "module {}".format(full_name),
                "register() failed: {}".format(exc),
            ) from exc

    @classmethod
    def _load_entry_point(cls, entry_point: object, source: str) -> object:
        try:
            candidate = entry_point.load()
        except Exception as exc:
            raise PluginLoadError(
                source,
                "load failed: {}".format(exc),
            ) from exc
        return cls._materialize_entry_point(candidate, source)

    @staticmethod
    def _materialize_entry_point(candidate: object, source: str) -> object:
        if isinstance(candidate, ModuleType):
            factory = getattr(candidate, "register", None)
            if not callable(factory):
                raise PluginLoadError(
                    source,
                    "module must expose a callable register() factory",
                )
            try:
                return factory()
            except Exception as exc:
                raise PluginLoadError(
                    source,
                    "register() failed: {}".format(exc),
                ) from exc

        # Entry points commonly expose a zero-argument plugin class. Check for a
        # class before checking for a plan attribute, because unbound methods on
        # the class are callable too.
        if isinstance(candidate, type):
            try:
                return candidate()
            except Exception as exc:
                raise PluginLoadError(
                    source,
                    "plugin class construction failed: {}".format(exc),
                ) from exc
        if callable(getattr(candidate, "plan", None)):
            return candidate
        if callable(candidate):
            try:
                return candidate()
            except Exception as exc:
                raise PluginLoadError(
                    source,
                    "factory failed: {}".format(exc),
                ) from exc
        return candidate

    @staticmethod
    def _entry_points_for_group(
        group: str,
        entry_points: Optional[Iterable[object]],
    ) -> list:
        if entry_points is not None:
            discovered = list(entry_points)
        else:
            try:
                discovered_entry_points = importlib_metadata.entry_points()
            except Exception as exc:
                raise PluginLoadError(
                    "entry point group {}".format(group),
                    "discovery failed: {}".format(exc),
                ) from exc

            selector = getattr(discovered_entry_points, "select", None)
            if callable(selector):
                discovered = list(selector(group=group))
            elif isinstance(discovered_entry_points, Mapping):
                discovered = list(discovered_entry_points.get(group, ()))
            else:
                discovered = [
                    entry_point
                    for entry_point in discovered_entry_points
                    if getattr(entry_point, "group", None) == group
                ]

        return [
            entry_point
            for entry_point in discovered
            if getattr(entry_point, "group", group) == group
        ]

    @staticmethod
    def _entry_point_sort_key(entry_point: object) -> Tuple[str, str, str]:
        distribution = getattr(entry_point, "dist", None)
        return (
            str(getattr(entry_point, "name", "")),
            str(getattr(entry_point, "value", "")),
            str(getattr(distribution, "name", "") or ""),
        )


__all__ = [
    "API_VERSION",
    "ENTRY_POINT_GROUP",
    "DuplicatePluginError",
    "PatternPlugin",
    "PluginCompatibilityError",
    "PluginError",
    "PluginLoadError",
    "PluginManifest",
    "PluginManifestError",
    "PluginRegistry",
    "validate_manifest",
    "validate_plugin",
]
