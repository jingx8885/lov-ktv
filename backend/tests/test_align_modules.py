"""Focused regression tests for the split alignment implementation."""

from lovktv.pipeline import align, audio, bounds, clock, energy, matching


def test_align_facade_only_owns_orchestration():
    """The facade exposes the top-level orchestration entry point only."""
    assert callable(align.align_lyrics)
    assert not hasattr(align, "vocal_regions")
    assert not hasattr(align, "asr_token_spans")


def test_focused_modules_are_independently_importable():
    """Each responsibility module can be imported without loading the facade first."""
    assert audio.HOP_MS == 20
    assert matching.EN_ACCEPT == 0.72
    assert bounds.MIN_LINE_MS == 500
    assert energy.ENERGY_HOLE_MAX_MS == 8000
