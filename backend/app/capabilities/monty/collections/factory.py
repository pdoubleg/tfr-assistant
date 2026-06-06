"""Registry assembly for Monty tool collections."""

from app.capabilities.monty.collections.base import MontyRuntimeContext
from app.capabilities.monty.collections.dataframe import DataframeOperationsCollection
from app.capabilities.monty.collections.deck_bundles import DeckBundlesCollection
from app.capabilities.monty.collections.files import FilesCollection
from app.capabilities.monty.collections.handles import HandlesCollection
from app.capabilities.monty.collections.report_bundles import ReportBundlesCollection
from app.capabilities.monty.collections.rlm import RLMCollection
from app.capabilities.monty.collections.visualizations import VisualizationsCollection
from app.capabilities.monty.registry import FunctionRegistry


def build_monty_registry(context: MontyRuntimeContext) -> FunctionRegistry:
    registry = FunctionRegistry()
    registry.register_collection(FilesCollection(context))
    registry.register_collection(HandlesCollection(context))
    registry.register_collection(DataframeOperationsCollection(context))
    registry.register_collection(RLMCollection(context))
    registry.register_collection(VisualizationsCollection(context))
    registry.register_collection(ReportBundlesCollection(context))
    registry.register_collection(DeckBundlesCollection(context))
    return registry
