"""Focused regression tests for the split alignment implementation."""

from lovktv.pipeline import audio, bounds, energy, matching, orchestrator


def test_orchestrator_owns_pipeline_composition():
    assert callable(orchestrator.align_lyrics)
    assert not hasattr(orchestrator, "vocal_regions")
    assert not hasattr(orchestrator, "asr_token_spans")


def test_focused_modules_are_independently_importable():
    """Each responsibility module can be imported independently."""
    assert audio.HOP_MS == 20
    assert matching.EN_ACCEPT == 0.72
    assert bounds.MIN_LINE_MS == 500
    assert energy.ENERGY_HOLE_MAX_MS == 8000
