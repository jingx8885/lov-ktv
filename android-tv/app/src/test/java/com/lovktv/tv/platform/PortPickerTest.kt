package com.lovktv.tv.platform

import com.lovktv.tv.platform.PortPicker
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.net.InetSocketAddress
import java.net.ServerSocket

class PortPickerTest {
    @Test
    fun firstFreeSkipsOccupiedPort() {
        ServerSocket().use { taken ->
            taken.reuseAddress = false
            taken.bind(InetSocketAddress("0.0.0.0", 0))
            val busy = taken.localPort
            assertFalse(PortPicker.available(busy))
            val free = PortPicker.firstFree(busy, 4)
            assertTrue(free != busy)
            assertTrue(PortPicker.available(free))
        }
    }
}
