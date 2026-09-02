package com.lovktv.tv.media

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class MediaCacheTest {
    @get:Rule
    val tmp = TemporaryFolder()

    @Test
    fun parseMediaPath() {
        assertEquals("abc" to "karaoke.m4a", MediaCache.parsePath("/media/abc/karaoke.m4a"))
        assertEquals("abc" to "lyrics.json", MediaCache.parsePath("/media/abc/lyrics.json?v=1"))
        assertNull(MediaCache.parsePath("/media/abc"))
        assertNull(MediaCache.parsePath("/media/../etc/passwd"))
        assertNull(MediaCache.parsePath("/api/songs"))
    }

    @Test
    fun wantedPlaybackFiles() {
        val remote = listOf(
            "original.mp3",
            "karaoke.m4a",
            "guide.m4a",
            "lyrics.json",
            "mtv.mp4",
            "skeleton.json",
            "cover.jpg",
            "vocals.wav",
            "asr.json",
        )
        // Both playback tracks precede the video: a song is pickable once it is
        // singable, and original.mp3 must not still be queued behind mtv.mp4.
        assertEquals(
            listOf("karaoke.m4a", "original.mp3", "lyrics.json", "guide.m4a", "skeleton.json", "cover.jpg", "mtv.mp4"),
            MediaCache.wantedFiles(remote),
        )
        val order = MediaCache.wantedFiles(remote)
        assertTrue(order.indexOf("original.mp3") < order.indexOf("mtv.mp4"))
        assertTrue(order.indexOf("original.mp3") < order.indexOf("lyrics.json"))
        assertTrue(MediaCache.isSingable(setOf("karaoke.m4a", "lyrics.json")))
        assertFalse(MediaCache.isSingable(setOf("karaoke.m4a")))
    }

    @Test
    fun writeAndReadCachedSong() {
        val cache = MediaCache(tmp.root)
        cache.writeSong(
            mapOf(
                "id" to "song1",
                "title" to "群青",
                "artist" to "YOASOBI",
                "language" to "ja",
                "status" to "ready",
                "media_rev" to "abc123def456",
            ),
            files = mapOf(
                "karaoke.m4a" to "AUDIO".toByteArray(),
                "lyrics.json" to """{"cues":[]}""".toByteArray(),
            ),
        )
        val song = cache.getSong("song1")!!
        assertEquals("群青", song.title)
        assertEquals("YOASOBI", song.artist)
        assertEquals("abc123def456", song.mediaRev)
        assertTrue(song.singable)
        assertTrue(cache.file("song1", "karaoke.m4a")!!.exists())
        assertEquals(1, cache.listSongs().size)
        assertEquals("AUDIO", cache.file("song1", "karaoke.m4a")!!.readText())
    }

    @Test
    fun parseByteRange() {
        assertEquals(0L to 99L, MediaCache.parseRange("bytes=0-99", 1000))
        assertEquals(100L to 999L, MediaCache.parseRange("bytes=100-", 1000))
        assertNull(MediaCache.parseRange(null, 1000))
    }

    @Test
    fun rejectUnsafeNames() {
        val cache = MediaCache(tmp.root)
        assertNull(cache.file("song1", "../x"))
        assertNull(cache.file("..", "karaoke.m4a"))
    }
}
