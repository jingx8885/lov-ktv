package com.lovktv.phone.network

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class HostParserTest {
    @Test
    fun parseTvHostEnablesLanMic() {
        val info = HostParser.parse(
            """{"origin":"http://192.168.1.8:8787","process_origin":"https://ktv.lovbrowser.com","mode":"tv","mic_port":18787,"mic_sample_rate":48000}""",
        )
        assertEquals("http://192.168.1.8:8787", info.origin)
        assertEquals("tv", info.mode)
        assertEquals(18787, info.micPort)
        assertEquals("192.168.1.8", HostParser.hostFromOrigin(info.origin))
        assertTrue(HostParser.lanMicReady(info))
    }

    @Test
    fun publicServerHasNoMic() {
        val info = HostParser.parse(
            """{"origin":"https://ktv.lovbrowser.com","process_origin":"https://ktv.lovbrowser.com","mode":"server","mic_port":0}""",
        )
        assertFalse(HostParser.lanMicReady(info))
    }
}
