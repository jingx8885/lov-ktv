"""Focused regression tests for the split alignment implementation."""

from lovktv.pipeline import align, audio, bounds, clock, energy, matching


def test_align_facade_preserves_historical_exports():
    """Public imports remain aliases to the focused implementations."""
    assert align.vocal_regions is audio.vocal_regions
    assert align.energy_token_spans is audio.energy_token_spans
    assert align.asr_token_spans is matching.asr_token_spans
    assert align.align_lines_to_asr is bounds.align_lines_to_asr
    assert align.align_lines_official_clock is clock.align_lines_official_clock
    assert align.merge_with_energy is energy.merge_with_energy


def test_focused_modules_are_independently_importable():
    """Each responsibility module can be imported without loading the facade first."""
    assert audio.HOP_MS == align.HOP_MS
    assert matching.EN_ACCEPT == align.EN_ACCEPT
    assert bounds.MIN_LINE_MS == align.MIN_LINE_MS
    assert energy.ENERGY_HOLE_MAX_MS == align.ENERGY_HOLE_MAX_MS
