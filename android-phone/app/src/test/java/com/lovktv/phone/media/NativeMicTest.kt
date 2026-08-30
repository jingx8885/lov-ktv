package com.lovktv.phone.media

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class NativeMicTest {
    @Test
    fun readyWhenHostAndPortPresent() {
        assertTrue(NativeMic.canStart("192.168.1.8", 18787))
    }

    @Test
    fun rejectMissingLan() {
        assertFalse(NativeMic.canStart("", 18787))
        assertFalse(NativeMic.canStart("192.168.1.8", 0))
        assertFalse(NativeMic.canStart("192.168.1.8", 70000))
    }

    @Test
    fun capabilitiesMarksTvWhenPortReady() {
        val json = NativeMic.capabilitiesJson("192.168.5.6", 18787, 48000)
        assertTrue(json.contains("\"native\":true"))
        assertTrue(json.contains("\"tv\":true"))
        assertTrue(json.contains("\"iem\":true"))
        assertTrue(json.contains("\"scan\":true"))
        assertTrue(json.contains("\"host\":\"192.168.5.6\""))
        assertTrue(json.contains("\"port\":18787"))
    }

    @Test
    fun capabilitiesHidesTvWithoutHost() {
        val json = NativeMic.capabilitiesJson("", 18787, 48000)
        assertTrue(json.contains("\"tv\":false"))
        assertTrue(json.contains("\"port\":0"))
    }

    @Test
    fun stateJsonRoundtripBits() {
        assertEquals("{\"tv\":true,\"iem\":false,\"gain\":80}", NativeMic.stateJson(true, false, 80))
        assertEquals("{\"tv\":false,\"iem\":true,\"gain\":0}", NativeMic.stateJson(false, true, -4))
    }

    @Test
    fun scalePcmMuteAndUnity() {
        val pcm = byteArrayOf(0x00, 0x10, 0x00, 0x20)
        NativeMic.scalePcm(pcm, 4, 100)
        assertEquals(0x10, pcm[1].toInt())
        NativeMic.scalePcm(pcm, 4, 0)
        assertEquals(0, pcm[0].toInt())
        assertEquals(0, pcm[1].toInt())
        assertEquals(0, pcm[2].toInt())
        assertEquals(0, pcm[3].toInt())
    }

    @Test
    fun playGainBoostsSliderToStayLevel() {
        assertEquals(220, NativeMic.playGainPct(100))
        assertEquals(176, NativeMic.playGainPct(80))
        val pcm = byteArrayOf(0x00, 0x10, 0x00, 0x20)
        NativeMic.scalePcm(pcm, 4, 200)
        assertEquals(0x20, pcm[1].toInt())
        assertEquals(0x40, pcm[3].toInt())
    }
}
