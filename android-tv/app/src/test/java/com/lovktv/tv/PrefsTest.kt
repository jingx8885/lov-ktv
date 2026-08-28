package com.lovktv.tv

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class PrefsTest {
    @Test
    fun defaultIsPublicHttps() {
        assertEquals("https://ktv.lovbrowser.com", Prefs.DEFAULT_SERVER)
        assertEquals("https://ktv.lovbrowser.com", Prefs.normalize(""))
        assertEquals("https://ktv.lovbrowser.com", Prefs.normalize("http://lov-ktv.local:8787"))
        assertEquals("https://ktv.lovbrowser.com", Prefs.normalize("ktv.lovbrowser.com"))
        assertEquals("https://ktv.lovbrowser.com", Prefs.normalize("http://ktv.lovbrowser.com"))
        assertEquals("https://ktv.lovbrowser.com", Prefs.normalize("  https://ktv.lovbrowser.com/  "))
    }

    @Test
    fun localKeepsHttp() {
        assertEquals("http://192.168.1.8:8787", Prefs.normalize("192.168.1.8:8787"))
        assertEquals("http://10.0.0.4:8787", Prefs.normalize("http://10.0.0.4:8787"))
        assertTrue(Prefs.looksLocal("lov-ktv.local"))
        assertFalse(Prefs.looksLocal("ktv.lovbrowser.com"))
        assertTrue(Prefs.isLegacyDefault("http://lov-ktv.local:8787"))
    }

    @Test
    fun roomCodeKeepsStableAlnum() {
        assertEquals("EABAB5", Prefs.validRoom("eabab5"))
        assertEquals("ABC123", Prefs.validRoom("  abc123  "))
        assertEquals("", Prefs.validRoom(""))
        assertEquals("", Prefs.validRoom("ab"))
        assertEquals("", Prefs.validRoom("not a room"))
    }
}
