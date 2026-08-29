package com.lovktv.phone.media

object LanMic {
    const val VERSION = 1
    const val HEADER = 12
    const val DEFAULT_PORT = 18787
    const val SAMPLE_RATE = 48000
    const val FRAME_MS = 10

    fun frameSamples(sampleRate: Int = SAMPLE_RATE): Int = sampleRate * FRAME_MS / 1000

    fun frameBytes(sampleRate: Int = SAMPLE_RATE): Int = frameSamples(sampleRate) * 2

    fun pack(seq: Int, sampleRate: Int, pcm: ByteArray, offset: Int = 0, length: Int = pcm.size): ByteArray {
        val out = ByteArray(HEADER + length)
        out[0] = 0x4C
        out[1] = 0x4B
        out[2] = 0x54
        out[3] = 0x4D
        out[4] = VERSION.toByte()
        out[5] = 0
        out[6] = ((seq ushr 8) and 0xFF).toByte()
        out[7] = (seq and 0xFF).toByte()
        out[8] = ((sampleRate ushr 24) and 0xFF).toByte()
        out[9] = ((sampleRate ushr 16) and 0xFF).toByte()
        out[10] = ((sampleRate ushr 8) and 0xFF).toByte()
        out[11] = (sampleRate and 0xFF).toByte()
        System.arraycopy(pcm, offset, out, HEADER, length)
        return out
    }

    data class Frame(val seq: Int, val sampleRate: Int, val pcm: ByteArray)

    fun unpack(packet: ByteArray, length: Int = packet.size): Frame? {
        if (length < HEADER) return null
        if (packet[0] != 0x4C.toByte() || packet[1] != 0x4B.toByte()) return null
        if (packet[2] != 0x54.toByte() || packet[3] != 0x4D.toByte()) return null
        if (packet[4].toInt() and 0xFF != VERSION) return null
        val seq = ((packet[6].toInt() and 0xFF) shl 8) or (packet[7].toInt() and 0xFF)
        val rate =
            ((packet[8].toInt() and 0xFF) shl 24) or
                ((packet[9].toInt() and 0xFF) shl 16) or
                ((packet[10].toInt() and 0xFF) shl 8) or
                (packet[11].toInt() and 0xFF)
        if (rate !in 8000..96000) return null
        return Frame(seq, rate, packet.copyOfRange(HEADER, length))
    }

    fun isNewerSeq(seq: Int, last: Int): Boolean {
        val delta = (seq - last) and 0xFFFF
        return delta != 0 && delta < 32768
    }
}
