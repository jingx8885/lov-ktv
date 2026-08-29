package com.lovktv.phone

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class LanHttpTest {
    @Test
    fun onlyPrivateHttpIsAllowed() {
        assertTrue(LanHttp.allowed("http://192.168.1.8:8788/api/rooms/EABAB5"))
        assertTrue(LanHttp.allowed("http://10.0.0.4/api/host"))
        assertFalse(LanHttp.allowed("https://ktv.lovbrowser.com/api/rooms/EABAB5"))
        assertFalse(LanHttp.allowed("http://ktv.lovbrowser.com/api/host"))
        assertFalse(LanHttp.allowed("https://192.168.1.8:8788/api/host"))
    }
}
