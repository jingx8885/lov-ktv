package com.lovktv.tv.ui

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class LyricClockTest {
    @Test
    fun matchingKaraokeAndMtvNeedNoLead() {
        assertEquals(0, LyricClock.videoLeadMs(242_901, 242_997))
        assertEquals(12_000, LyricClock.videoSeekMs(12_000, 242_901, 242_997))
    }

    @Test
    fun longerMtvIntroLeadsVideo() {
        assertEquals(8_800, LyricClock.videoLeadMs(251_700, 242_900))
        assertEquals(20_800, LyricClock.videoSeekMs(12_000, 251_700, 242_900))
    }

    @Test
    fun tinyDriftDoesNotSeek() {
        assertFalse(LyricClock.shouldSeek(12_050, 12_000, 0L, 3_000L))
        assertFalse(LyricClock.shouldSeek(12_400, 12_000, 0L, 3_000L))
        assertTrue(LyricClock.shouldSeek(13_000, 12_000, 0L, 3_000L))
        assertFalse(LyricClock.shouldSeek(13_000, 12_000, 2_500L, 3_000L))
    }

    fun unstartedClockDoesNotSeek() {
        assertFalse(LyricClock.shouldSeek(0, 12_000, 0L, 1_000L, true))
        assertFalse(LyricClock.shouldSeek(12_000, 12_000, 0L, 1_000L, false))
    }
}
