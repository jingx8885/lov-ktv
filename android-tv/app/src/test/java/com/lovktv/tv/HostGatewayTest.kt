package com.lovktv.tv

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class HostGatewayTest {
    @Test
    fun phoneUrlUsesLanOriginAndRoom() {
        val url = HostGateway.phoneUrl("http://192.168.1.8:8787", "EABAB5")
        assertEquals("http://192.168.1.8:8787/m.html?room=EABAB5", url)
    }

    @Test
    fun localPathsStayOnTvBox() {
        assertTrue(HostGateway.isLocalPath("/api/host"))
        assertTrue(HostGateway.isLocalPath("/tv.html"))
        assertTrue(HostGateway.isLocalPath("/m.html"))
        assertTrue(HostGateway.isLocalPath("/app.css"))
        assertTrue(HostGateway.isLocalPath("/vendor/qrcode.js"))
        assertFalse(HostGateway.isLocalPath("/api/songs"))
        assertFalse(HostGateway.isLocalPath("/media/abc/karaoke.m4a"))
        assertFalse(HostGateway.isLocalPath("/ws/rooms/EABAB5"))
    }

    @Test
    fun remoteUrlJoinsProcessServerAndPath() {
        val url = HostGateway.remoteUrl("http://10.0.2.2:8787", "/api/search", "q=群青")
        assertEquals("http://10.0.2.2:8787/api/search?q=群青", url)
    }

    @Test
    fun pickLanPrefersPrivateIpv4() {
        assertEquals(
            "192.168.1.8",
            HostGateway.pickLanAddress(listOf("127.0.0.1", "192.168.1.8", "10.0.2.15")),
        )
        assertEquals(
            "10.0.0.4",
            HostGateway.pickLanAddress(listOf("127.0.0.1", "10.0.0.4")),
        )
        assertEquals("", HostGateway.pickLanAddress(listOf("127.0.0.1")))
    }

    @Test
    fun hostPayloadForTvBox() {
        val payload = HostGateway.hostPayload(
            lanOrigin = "http://192.168.1.8:8787",
            processOrigin = "http://10.0.2.2:8787",
            room = "EABAB5",
        )
        assertEquals("tv", payload.mode)
        assertEquals("http://192.168.1.8:8787", payload.origin)
        assertEquals("http://10.0.2.2:8787", payload.processOrigin)
        assertEquals("/m.html?room=EABAB5", payload.phonePath)
        assertEquals(
            "http://192.168.1.8:8787/m.html?room=EABAB5&process=http%3A%2F%2F10.0.2.2%3A8787",
            payload.phoneUrl,
        )
        assertEquals("EABAB5", payload.room)
        assertEquals(0, payload.cacheReady)
        assertEquals(18787, payload.micPort)
        assertEquals(48000, payload.micSampleRate)
        val json = HostGateway.toJson(payload)
        assertTrue(json.contains("\"cache_ready\":0"))
        assertTrue(json.contains("\"mic_port\":18787"))
        assertTrue(json.contains("\"mic_sample_rate\":48000"))
        assertTrue(json.contains("\"room\":\"EABAB5\""))
    }

    @Test
    fun hostPayloadPhoneUrlUsesLanPageAndProcessCatalog() {
        val payload = HostGateway.hostPayload(
            lanOrigin = "http://192.168.1.8:8788",
            processOrigin = "https://ktv.lovbrowser.com",
            room = "EABAB5",
        )
        assertEquals("http://192.168.1.8:8788", payload.origin)
        assertEquals("https://ktv.lovbrowser.com", payload.processOrigin)
        assertEquals(
            "http://192.168.1.8:8788/m.html?room=EABAB5&process=https%3A%2F%2Fktv.lovbrowser.com",
            payload.phoneUrl,
        )
    }

    @Test
    fun classifyApiForCacheFallback() {
        assertEquals(ApiKind.SongsList, HostGateway.classify("/api/songs", "GET"))
        assertEquals(ApiKind.Song("abc"), HostGateway.classify("/api/songs/abc", "GET"))
        assertEquals(ApiKind.RoomCreate, HostGateway.classify("/api/rooms", "POST"))
        assertEquals(ApiKind.RoomGet(""), HostGateway.classify("/api/rooms", "GET"))
        assertEquals(ApiKind.RoomGet("EABAB5"), HostGateway.classify("/api/rooms/eabab5", "GET"))
        assertEquals(ApiKind.RoomSkip("EABAB5"), HostGateway.classify("/api/rooms/EABAB5/skip", "POST"))
        assertEquals(ApiKind.RoomQueue("EABAB5"), HostGateway.classify("/api/rooms/EABAB5/queue", "POST"))
        assertEquals(ApiKind.Media("abc", "karaoke.m4a"), HostGateway.classify("/media/abc/karaoke.m4a", "GET"))
        assertEquals(ApiKind.Proxy, HostGateway.classify("/api/search", "GET"))
    }
}
