package com.lovktv.phone

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class PrefsTest {
    @Test
    fun normalizeAddsScheme() {
        assertEquals("https://ktv.lovbrowser.com", Prefs.normalize("ktv.lovbrowser.com"))
        assertEquals("http://192.168.1.8:8787", Prefs.normalize("192.168.1.8:8787"))
        assertEquals("http://lov-ktv.local:8787", Prefs.normalize("lov-ktv.local:8787"))
        assertEquals("https://ktv.lovbrowser.com", Prefs.normalize("  https://ktv.lovbrowser.com/  "))
    }

    @Test
    fun looksLocalDetectsPrivateIpv4() {
        assertTrue(Prefs.looksLocal("192.168.1.8"))
        assertTrue(Prefs.looksLocal("10.0.0.4"))
        assertTrue(Prefs.looksLocal("lov-ktv.local"))
        assertFalse(Prefs.looksLocal("ktv.lovbrowser.com"))
    }
}
