package com.lovktv.tv

import java.io.IOException
import java.net.InetSocketAddress
import java.net.ServerSocket

object PortPicker {
    fun firstFree(preferred: Int, count: Int = 8): Int {
        for (offset in 0 until count) {
            val port = preferred + offset
            if (available(port)) return port
        }
        throw IOException("无法绑定局域网端口")
    }

    fun available(port: Int): Boolean {
        if (port !in 1..65535) return false
        return try {
            ServerSocket().use { socket ->
                socket.reuseAddress = false
                socket.bind(InetSocketAddress("0.0.0.0", port))
            }
            true
        } catch (_: Exception) {
            false
        }
    }
}
