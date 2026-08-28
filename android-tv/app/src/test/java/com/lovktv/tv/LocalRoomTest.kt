package com.lovktv.tv

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class LocalRoomTest {
    private val songs = listOf(
        CachedSong("s1", "群青", "YOASOBI", "ja", "ready", listOf("karaoke.m4a", "lyrics.json"), true),
        CachedSong("s2", "夜に駆ける", "YOASOBI", "ja", "ready", listOf("karaoke.m4a", "lyrics.json"), true),
        CachedSong("busy", "制作中", "x", "zh", "separating", emptyList(), false),
    )

    @Test
    fun enqueueSkipAndPlayCachedSongs() {
        val room = LocalRoom(songLookup = { id -> songs.firstOrNull { it.id == id } })
        val created = room.ensure("OFF1")
        assertEquals("OFF1", created.code)
        room.enqueue("OFF1", "s1")
        var snap = room.enqueue("OFF1", "s2")
        assertEquals(listOf("s1", "s2"), snap.queue.map { it.songId })
        assertEquals("s1", snap.nowPlaying?.songId)

        snap = room.skip("OFF1")
        assertEquals(listOf("s2"), snap.queue.map { it.songId })
        assertEquals("s2", snap.nowPlaying?.songId)

        snap = room.enqueue("OFF1", "s1")
        val item = snap.queue.first { it.songId == "s1" }
        snap = room.playNow("OFF1", itemId = item.id)
        assertEquals("s1", snap.nowPlaying?.songId)
    }

    @Test
    fun rejectSongThatIsNotReady() {
        val room = LocalRoom(songLookup = { id -> songs.firstOrNull { it.id == id } })
        room.ensure("OFF2")
        try {
            room.enqueue("OFF2", "busy")
            throw AssertionError("should fail")
        } catch (exc: IllegalArgumentException) {
            assertTrue(exc.message!!.contains("还没就绪"))
        }
        val snap = room.enqueue("OFF2", "missing")
        assertEquals("missing", snap.nowPlaying?.songId)
        assertEquals("ready", snap.nowPlaying?.status)
    }

    @Test
    fun ensureWithoutCodeReusesSameRoom() {
        val room = LocalRoom(songLookup = { id -> songs.firstOrNull { it.id == id } })
        val first = room.ensure(null)
        val second = room.ensure(null)
        assertEquals(first.code, second.code)
        assertTrue(first.code.matches(Regex("^[A-Z0-9]{4,12}$")))
    }

    @Test
    fun importRemoteSnapshotThenWorkOffline() {
        val room = LocalRoom(songLookup = { id -> songs.firstOrNull { it.id == id } })
        room.importSnapshot(
            """{"code":"EABAB5","vocal_mix":0,"volume":70,"mic_gain":80,"now_index":0,
              "queue":[{"id":"q1","song_id":"s1","position":1,"title":"群青","artist":"YOASOBI","status":"ready","language":"ja"}],
              "now_playing":{"id":"q1","song_id":"s1","position":1,"title":"群青","artist":"YOASOBI","status":"ready","language":"ja"}}""",
        )
        val snap = room.snapshot("EABAB5")
        assertEquals("s1", snap.nowPlaying?.songId)
        assertEquals(70, snap.volume)
        val skipped = room.skip("EABAB5")
        assertTrue(skipped.queue.isEmpty())
        assertNull(skipped.nowPlaying)
    }
}
