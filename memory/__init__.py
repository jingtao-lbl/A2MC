"""
Adaptive Memory System for A2MC

This module provides persistent memory for the A2MC calibration framework,
enabling learning from experiments and preventing repetition of failed approaches.

Two JSON knowledge layers:
- Model knowledge, true of a model on any site. The path depends on the model:
  memory/gained_knowledge/ for FATES (unprefixed: FATES predates the per-model layout),
  memory/<model>/gained_knowledge/ for adapter models (ecosim, pflotran).
  tools/model_knowledge_store.py resolves the active model's store.
- Case knowledge: use_cases/{Model}_{Case}/memory/gained_knowledge/

Components:
- MemoryManager: Main interface for querying and updating memory
- store: JSON persistence utilities

Usage:
    from memory import MemoryManager

    # Initialize with the FATES model store (other models: ./memory/<model>/gained_knowledge)
    memory = MemoryManager("./memory/gained_knowledge")

    # Initialize with site-specific knowledge
    memory = MemoryManager("./use_cases/ELM-FATES_Kougarok/memory/gained_knowledge")

    # Query relevant context for diagnosis
    context = memory.get_relevant_context(["froot_pft10", "leaf_pft10"])

    # Record experiment outcome
    memory.record_experiment(experiment, results, outcome="FAILED")

    # Add new discovery
    memory.add_discovery(
        name="new_finding",
        description="Description of finding",
        mechanism="Mechanistic explanation",
        affects=["froot_pft10"],
        source="auto_discovered"
    )
"""

from .manager import MemoryManager
from .store import load_json, save_json

__all__ = ["MemoryManager", "load_json", "save_json"]
__version__ = "0.1.0"
