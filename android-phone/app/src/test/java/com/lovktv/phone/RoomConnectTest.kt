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
}
