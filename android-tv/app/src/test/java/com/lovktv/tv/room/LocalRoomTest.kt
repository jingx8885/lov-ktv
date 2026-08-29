package com.lovktv.tv.room

import com.lovktv.tv.media.CachedSong

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class LocalRoomTest {
    private val songs = listOf(
        CachedSong("s1", "群青", "YOASOBI", "ja", "ready", listOf("karaoke.m4a", "lyrics.json"), true, "rev-s1"),
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
        assertEquals("rev-s1", snap.nowPlaying?.mediaRev)

        snap = room.skip("OFF1")
        assertEquals(listOf("s2"), snap.queue.map { it.songId })
        assertEquals("s2", snap.nowPlaying?.songId)
        assertEquals(0, snap.nowIndex)

        snap = room.enqueue("OFF1", "s1")
        val item = snap.queue.first { it.songId == "s1" }
        snap = room.playNow("OFF1", itemId = item.id)
        assertEquals("s1", snap.nowPlaying?.songId)
    }

    @Test
    fun queuesUncachedSongsAndRefreshesWhenReady() {
        val live = songs.associateBy { it.id }.toMutableMap()
        val room = LocalRoom(songLookup = { id -> live[id] })
        room.ensure("OFF2")
        var snap = room.enqueue("OFF2", "busy")
        assertEquals("separating", snap.nowPlaying?.status)
        snap = room.enqueue("OFF2", "missing")
        assertEquals(listOf("busy", "missing"), snap.queue.map { it.songId })
        assertEquals("fetching", snap.queue.first { it.songId == "missing" }.status)
        live["missing"] = CachedSong("missing", "新歌", "x", "zh", "ready", listOf("karaoke.m4a"), true, "rev-m")
        room.refreshSong("missing")
        snap = room.snapshot("OFF2")
        val missing = snap.queue.first { it.songId == "missing" }
        assertEquals("ready", missing.status)
        assertEquals("新歌", missing.title)
        assertEquals("rev-m", missing.mediaRev)
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
        assertEquals("rev-s1", snap.nowPlaying?.mediaRev)
        assertEquals(70, snap.volume)
        val skipped = room.skip("EABAB5")
        assertTrue(skipped.queue.isEmpty())
        assertNull(skipped.nowPlaying)
        val paused = room.setMix("EABAB5", paused = true)
        assertTrue(paused.paused)
        assertFalse(room.setMix("EABAB5", paused = false).paused)
    }
}
