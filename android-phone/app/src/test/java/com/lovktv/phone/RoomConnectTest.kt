package com.lovktv.phone

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class RoomConnectTest {
    @Test
    fun catalogUsesProcessOriginWhenScannedTv() {
        val host = HostParser.parse(
            """{"origin":"http://192.168.1.8:8788","process_origin":"https://ktv.lovbrowser.com","mode":"tv","mic_port":18787,"mic_sample_rate":48000}""",
        )
        assertEquals(
            "https://ktv.lovbrowser.com",
            RoomConnect.catalogServer("http://192.168.1.8:8788", host),
        )
    }

    @Test
    fun catalogStaysPublicWhenScannedCloud() {
        val host = HostParser.parse(
            """{"origin":"https://ktv.lovbrowser.com","process_origin":"https://ktv.lovbrowser.com","mode":"server","mic_port":0}""",
        )
        assertEquals(
            "https://ktv.lovbrowser.com",
            RoomConnect.catalogServer("https://ktv.lovbrowser.com", host),
        )
    }

    @Test
    fun pickMicUsesTvLanHost() {
        val cloud = HostParser.parse(
            """{"origin":"https://ktv.lovbrowser.com","process_origin":"https://ktv.lovbrowser.com","mode":"server","mic_port":0}""",
        )
        val tv = HostParser.parse(
            """{"origin":"http://192.168.1.8:8788","process_origin":"https://ktv.lovbrowser.com","mode":"tv","mic_port":18787,"mic_sample_rate":48000}""",
        )
        val mic = RoomConnect.pickMic(cloud, tv)!!
        assertTrue(HostParser.lanMicReady(mic))
        assertEquals("192.168.1.8", HostParser.hostFromOrigin(mic.origin))
        assertEquals(18787, mic.micPort)
        assertNull(RoomConnect.pickMic(cloud))
    }

    @Test
    fun catalogFallsBackToPublicWhenTvHasNoProcess() {
        val host = HostParser.parse(
            """{"origin":"http://192.168.1.8:8788","process_origin":"","mode":"tv","mic_port":18787}""",
        )
        assertEquals(
            "https://ktv.lovbrowser.com",
            RoomConnect.catalogServer("http://192.168.1.8:8788", host),
        )
    }

    @Test
    fun lanOriginUsesHintOrLocalScan() {
        val public = HostParser.parse(
            """{"origin":"https://ktv.lovbrowser.com","process_origin":"https://ktv.lovbrowser.com","mode":"server","mic_port":0}""",
        )
        val tv = HostParser.parse(
            """{"origin":"http://192.168.1.8:8788","process_origin":"https://ktv.lovbrowser.com","mode":"tv","mic_port":0}""",
        )
        assertEquals(
            "http://192.168.1.8:8788",
            RoomConnect.lanOrigin("https://ktv.lovbrowser.com", "http://192.168.1.8:8788", public),
        )
        assertEquals(
            "http://192.168.1.8:8788",
            RoomConnect.lanOrigin("http://192.168.1.8:8788", "", tv),
        )
        assertEquals("", RoomConnect.lanOrigin("https://ktv.lovbrowser.com", "", public))
        assertEquals("http://192.168.1.8:8788", RoomConnect.roomOrigin("https://ktv.lovbrowser.com", "http://192.168.1.8:8788"))
        assertEquals("https://ktv.lovbrowser.com", RoomConnect.roomOrigin("https://ktv.lovbrowser.com", ""))
    }

    @Test
    fun fromQrWritesScannedRoomEvenWithoutHost() {
        val session = RoomConnect.fromQr(
            "https://ktv.lovbrowser.com",
            "b830c8",
            "http://192.168.1.8:8788",
        )
        assertEquals("https://ktv.lovbrowser.com", session.server)
        assertEquals("B830C8", session.room)
        assertEquals("http://192.168.1.8:8788", session.lanOrigin)
        assertEquals("192.168.1.8", session.micHost)
        assertEquals(0, session.micPort)
    }

    @Test
    fun fromQrUsesTvHostMicAndDoesNotKeepOldRoom() {
        val tv = HostParser.parse(
            """{"origin":"http://192.168.5.6:8788","process_origin":"https://ktv.lovbrowser.com","mode":"tv","mic_port":18787,"mic_sample_rate":48000}""",
        )
        val first = RoomConnect.fromQr("https://ktv.lovbrowser.com", "OLD123", "http://192.168.1.8:8788")
        val next = RoomConnect.fromQr(
            "http://192.168.5.6:8788",
            "new456",
            "http://192.168.5.6:8788",
            tv,
            tv,
        )
        assertEquals("OLD123", first.room)
        assertEquals("NEW456", next.room)
        assertEquals("https://ktv.lovbrowser.com", next.server)
        assertEquals("http://192.168.5.6:8788", next.lanOrigin)
        assertEquals("192.168.5.6", next.micHost)
        assertEquals(18787, next.micPort)
        assertEquals(48000, next.micRate)
    }

    @Test
    fun lanFromRoomUsesPrivateOrigin() {
        val room = Models.room(
            """{"code":"HOME01","lan_origin":"http://192.168.1.8:8788/","lan_mic_port":18787,"queue":[]}""",
        )
        assertEquals("http://192.168.1.8:8788", RoomConnect.lanFromRoom(room))
        assertEquals("https://ktv.lovbrowser.com", RoomConnect.catalogOf("http://192.168.1.8:8788"))
        val public = Models.room("""{"code":"HOME01","lan_origin":"https://ktv.lovbrowser.com","queue":[]}""")
        assertEquals("", RoomConnect.lanFromRoom(public))
    }
}
