package com.lovktv.tv.network

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class LanDirectoryTest {
    @Test
    fun publishesWhenOriginChangesOrHeartbeatExpires() {
        assertTrue(LanDirectory.shouldPublish("", "http://192.168.1.8:8788", 0, 10_000))
        assertFalse(LanDirectory.shouldPublish("http://192.168.1.8:8788", "http://192.168.1.8:8788", 1_000, 5_000))
        assertTrue(LanDirectory.shouldPublish("http://192.168.1.8:8788", "http://192.168.1.9:8788", 1_000, 2_000))
        assertTrue(
            LanDirectory.shouldPublish(
                "http://192.168.1.8:8788",
                "http://192.168.1.8:8788",
                1_000,
                1_000 + LanDirectory.HEARTBEAT_MS,
            ),
        )
    }

    @Test
    fun publishBodyIncludesLanAndLocalUrl() {
        val body = LanDirectory.publishBody("http://192.168.1.8:8788/", 18787, 48000)
        assertTrue(body.contains("\"lan_origin\":\"http://192.168.1.8:8788\""))
        assertTrue(body.contains("\"local_url\":\"http://192.168.1.8:8788\""))
        assertTrue(body.contains("\"mic_port\":18787"))
        assertEquals("http://192.168.5.6:8788", LanDirectory.lanFromRoom("""{"code":"A1","lan_origin":"http://192.168.5.6:8788"}"""))
        assertEquals("http://192.168.5.6:8788", LanDirectory.lanFromRoom("""{"local_url":"http://192.168.5.6:8788/"}"""))
    }
}
