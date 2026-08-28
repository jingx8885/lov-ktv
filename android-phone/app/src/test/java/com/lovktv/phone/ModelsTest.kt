package com.lovktv.phone

import org.junit.Assert.assertEquals
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
            """{"code":"eabab5","now_playing":{"title":"群青","artist":"YOASOBI"},"queue":[{"song_id":"s1","title":"群青","artist":"YOASOBI","status":"ready"}]}""",
        )
        assertEquals("EABAB5", room.code)
        assertEquals("群青", room.nowTitle)
        assertEquals("s1", room.queue[0].id)
        assertTrue(room.queue[0].ready)
    }
}
