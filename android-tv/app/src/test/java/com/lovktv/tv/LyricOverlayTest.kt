package com.lovktv.tv

import org.junit.Assert.assertEquals
import org.junit.Test

class LyricOverlayTest {
    @Test
    fun joinsJapaneseAndGloss() {
        assertEquals("ポケモン ゲットだぜーッ!\n宝可梦我抓到你了", LyricOverlay.visibleText("ポケモン ゲットだぜーッ!", "宝可梦我抓到你了"))
    }

    @Test
    fun skipsBlankOrDuplicateGloss() {
        assertEquals("群青", LyricOverlay.visibleText("群青", ""))
        assertEquals("群青", LyricOverlay.visibleText("群青", "群青"))
        assertEquals("中文", LyricOverlay.visibleText("  ", "中文"))
        assertEquals("", LyricOverlay.visibleText("", ""))
    }
}
