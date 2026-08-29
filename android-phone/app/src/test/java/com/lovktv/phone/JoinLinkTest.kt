package com.lovktv.phone

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class JoinLinkTest {
    @Test
    fun parseTvPhoneQr() {
        val target = JoinLink.parse("http://192.168.1.8:8787/m.html?room=EABAB5&v=queue3")
        assertEquals("http://192.168.1.8:8787", target!!.server)
        assertEquals("EABAB5", target.room)
    }

    @Test
    fun parseLoginScanQr() {
        val target = JoinLink.parse("http://192.168.1.8:8787/api/auth/scan?ticket=abc123&room=eabab5")
        assertEquals("http://192.168.1.8:8787", target!!.server)
        assertEquals("EABAB5", target.room)
    }

    @Test
    fun parseTvPageQr() {
        val target = JoinLink.parse("https://ktv.lovbrowser.com/tv.html?room=B0EBAE")
        assertEquals("https://ktv.lovbrowser.com", target!!.server)
        assertEquals("B0EBAE", target.room)
    }

    @Test
    fun parseBareRoomUsesFallbackServer() {
        val target = JoinLink.parse("abc123", "192.168.1.8:8787")
        assertEquals("http://192.168.1.8:8787", target!!.server)
        assertEquals("ABC123", target.room)
    }

    @Test
    fun parseRejectsNoise() {
        assertNull(JoinLink.parse(""))
        assertNull(JoinLink.parse("http://192.168.1.8:8787/"))
        assertNull(JoinLink.parse("https://example.com/about"))
        assertNull(JoinLink.parse("hello world"))
    }

    @Test
    fun parsePublicQrKeepsLanForMic() {
        val encoded = JoinLink.parse(
            "https://ktv.lovbrowser.com/m.html?room=EABAB5&v=queue3&lan=http%3A%2F%2F192.168.1.8%3A8788",
        )
        assertEquals("https://ktv.lovbrowser.com", encoded!!.server)
        assertEquals("EABAB5", encoded.room)
        assertEquals("http://192.168.1.8:8788", encoded.lan)

        val raw = JoinLink.parse(
            "https://ktv.lovbrowser.com/m.html?room=EABAB5&v=queue3&lan=http://192.168.1.8:8788",
        )
        assertEquals("http://192.168.1.8:8788", raw!!.lan)
    }
}

class DeskPageTest {
    @Test
    fun lanDeskOpensLocalMHtml() {
        val url = DeskPage.url(
            "https://ktv.lovbrowser.com",
            "eabab5",
            "http://192.168.1.8:8788",
        )
        assertEquals(
            "http://192.168.1.8:8788/m.html?room=EABAB5&v=scan2&androidphone=1&process=https%3A%2F%2Fktv.lovbrowser.com",
            url,
        )
    }

    @Test
    fun publicDeskWhenNoLan() {
        val url = DeskPage.url("https://ktv.lovbrowser.com", "ABC123", "")
        assertEquals("https://ktv.lovbrowser.com/m.html?room=ABC123&v=scan2&androidphone=1", url)
    }

    @Test
    fun publicDeskAllowsEmptyRoom() {
        val url = DeskPage.url("https://ktv.lovbrowser.com", "", "")
        assertEquals("https://ktv.lovbrowser.com/m.html?room=&v=scan2&androidphone=1", url)
    }
}
