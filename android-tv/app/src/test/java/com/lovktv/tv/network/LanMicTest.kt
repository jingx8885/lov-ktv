package com.lovktv.tv.network

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class LanMicTest {
    @Test
    fun packAndUnpackRoundTrip() {
        val pcm = ByteArray(LanMic.frameBytes()) { index -> (index % 251).toByte() }
        val packet = LanMic.pack(42, 48000, pcm)
        val frame = LanMic.unpack(packet)
        assertNotNull(frame)
        assertEquals(42, frame!!.seq)
        assertEquals(48000, frame.sampleRate)
        assertTrue(pcm.contentEquals(frame.pcm))
    }

    @Test
    fun rejectShortOrBadMagic() {
        assertNull(LanMic.unpack(ByteArray(8)))
        val pcm = ByteArray(16)
        val packet = LanMic.pack(1, 48000, pcm)
        packet[0] = 'X'.code.toByte()
        assertNull(LanMic.unpack(packet))
    }

    @Test
    fun seqWrapIsNewer() {
        assertTrue(LanMic.isNewerSeq(0, 65535))
        assertTrue(LanMic.isNewerSeq(2, 65534))
        assertFalse(LanMic.isNewerSeq(10, 20))
        assertFalse(LanMic.isNewerSeq(20, 20))
    }
}
