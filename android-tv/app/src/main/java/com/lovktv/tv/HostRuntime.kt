package com.lovktv.tv

object HostRuntime {
    const val DEFAULT_PORT = 8787

    @Volatile
    var port: Int = DEFAULT_PORT

    @Volatile
    var ready: Boolean = false

    @Volatile
    var lanOrigin: String = ""

    @Volatile
    var processOrigin: String = ""

    @Volatile
    var micPort: Int = 0
}
