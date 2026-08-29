package com.lovktv.phone

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
}
