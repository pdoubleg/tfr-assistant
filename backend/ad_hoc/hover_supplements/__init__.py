"""Standalone Hover supplement research. Import individual modules for lighter dependencies."""

from .agents import extract_baseline, extract_claim, extract_supplement
from .analysis import decompose_dollar_difference, mechanism_analysis, scorecards, stratified_sample
from .contracts import ClaimBundle, Evidence, ExtractionResult
from .dataframes import build_feature_table, concat_feature_frames, feature_dictionary
from .modeling import ResearchConfig, fit_statistical_models, run_predictive_research
from .models import BaselineClaimFeatures, ClaimLLMFeatures, SupplementMechanismFeatures
from .runner import extract_batch, run_analysis, write_report

__all__ = [
    "BaselineClaimFeatures",
    "ClaimBundle",
    "ClaimLLMFeatures",
    "Evidence",
    "ExtractionResult",
    "ResearchConfig",
    "SupplementMechanismFeatures",
    "build_feature_table",
    "concat_feature_frames",
    "decompose_dollar_difference",
    "extract_baseline",
    "extract_batch",
    "extract_claim",
    "extract_supplement",
    "feature_dictionary",
    "fit_statistical_models",
    "mechanism_analysis",
    "run_analysis",
    "run_predictive_research",
    "scorecards",
    "stratified_sample",
    "write_report",
]
