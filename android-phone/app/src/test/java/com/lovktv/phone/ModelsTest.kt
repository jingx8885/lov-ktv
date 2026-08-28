package com.lovktv.phone

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ModelsTest {
    @Test
    fun parseSearchHitsAndRoom() {
        val hits = Models.hits(
            """{"hits":[{"id":"k1","title":"群青","artist":"YOASOBI","source":"mugen","language":"ja"}]}""",
        )
        assertEquals(1, hits.size)
        assertEquals("群青", hits[0].title)
        assertTrue(hits[0].isMv)
        val room = Models.room(
            """{"code":"eabab5","vocal_mix":0,"volume":70,"now_index":0,
              "now_playing":{"id":"q1","song_id":"s1","title":"群青","artist":"YOASOBI","status":"ready"},
              "queue":[
                {"id":"q1","song_id":"s1","title":"群青","artist":"YOASOBI","status":"ready"},
                {"id":"q2","song_id":"s2","title":"夜に駆ける","artist":"YOASOBI","status":"ready"},
                {"id":"q3","song_id":"s3","title":"残响散歌","artist":"Aimer","status":"ready"}
              ]}""",
        )
        assertEquals("EABAB5", room.code)
        assertEquals("群青", room.nowTitle)
        assertEquals("q1", room.queue[0].id)
        assertEquals("s1", room.queue[0].songId)
        assertTrue(room.queue[0].ready)
        assertFalse(room.vocalOn)
        assertEquals(70, room.volume)
        assertFalse(Models.canBump(0, 0))
        assertFalse(Models.canBump(1, 0))
        assertTrue(Models.canBump(2, 0))
    }

    @Test
    fun librarySongUsesIdAsSongId() {
        val songs = Models.songs(
            """{"songs":[{"id":"s9","title":"晴天","artist":"周杰伦","status":"ready","language":"zh"}]}""",
        )
        assertEquals("s9", songs[0].id)
        assertEquals("s9", songs[0].songId)
        assertTrue(songs[0].ready)
    }
}
