package com.lovktv.tv

import java.net.Inet4Address
import java.net.NetworkInterface

object LanAddress {
    fun ipv4Candidates(): List<String> {
        val found = mutableListOf<String>()
        val interfaces = NetworkInterface.getNetworkInterfaces() ?: return found
        for (iface in interfaces) {
            if (!iface.isUp || iface.isLoopback) continue
            for (address in iface.inetAddresses) {
                if (address is Inet4Address && !address.isLoopbackAddress) {
                    address.hostAddress?.let(found::add)
                }
            }
        }
        return found
    }

    fun pick(fallback: String = "127.0.0.1"): String {
        return HostGateway.pickLanAddress(ipv4Candidates()).ifBlank { fallback }
    }

    fun origin(port: Int): String {
        return "http://${pick()}:$port"
    }
}
