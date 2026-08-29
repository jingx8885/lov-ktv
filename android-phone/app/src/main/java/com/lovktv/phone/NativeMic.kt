package com.lovktv.phone

object NativeMic {
    fun canStart(host: String, port: Int): Boolean {
        return host.isNotBlank() && port in 1..65535
    }
}
