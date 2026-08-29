package com.lovktv.tv

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AssetRevTest {
    @Test
    fun rewriteVersionsFrontendRefsAndKeepsMedia() {
        val src = """
            import { x } from "./mix.js";
            import { y } from "./tick.js?v=native1";
            <script type="module" src="/tv/app.js"></script>
            <link rel="stylesheet" href="/tv/stage/css/stage.css?v=split10" />
            addModule("/shared/audio/js/aec-worklet.js");
            @import url("/shared/ui/css/tokens.css");
            const lyrics = `/media/${'$'}{id}/lyrics.json?v=ja-kanji`;
            const stem = `/media/${'$'}{id}/karaoke.m4a?v=stem2`;
        """.trimIndent()
        val out = AssetRev.rewrite(src, "abc123")
        assertTrue(out.contains("""from "./mix.js?v=abc123""""))
        assertTrue(out.contains("""from "./tick.js?v=abc123""""))
        assertTrue(out.contains("""src="/tv/app.js?v=abc123""""))
        assertTrue(out.contains("""href="/tv/stage/css/stage.css?v=abc123""""))
        assertTrue(out.contains("""addModule("/shared/audio/js/aec-worklet.js?v=abc123")"""))
        assertTrue(out.contains("""@import url("/shared/ui/css/tokens.css?v=abc123")"""))
        assertTrue(out.contains("`/media/\${id}/lyrics.json?v=ja-kanji`"))
        assertTrue(out.contains("`/media/\${id}/karaoke.m4a?v=stem2`"))
    }

    @Test
    fun blankRevLeavesTextAlone() {
        val src = """import "./install.js";"""
        assertEquals(src, AssetRev.rewrite(src, ""))
    }

    @Test
    fun shouldRewriteOnlyTextAssets() {
        assertTrue(AssetRev.shouldRewrite("web/tv.html"))
        assertTrue(AssetRev.shouldRewrite("web/tv/app.js"))
        assertTrue(AssetRev.shouldRewrite("web/phone/shell/css/shell.css"))
        assertFalse(AssetRev.shouldRewrite("web/brand/icon.png"))
    }

    @Test
    fun manifestRevisionIsTheEmbeddedAssetRevision() {
        assertEquals("abc123", AssetRev.fromManifestJson("{\"revision\":\"abc123\"}"))
        assertEquals("", AssetRev.fromManifestJson("{}"))
    }
}
