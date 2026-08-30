package com.lovktv.tv.network


import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import android.os.Build
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetSocketAddress
import kotlin.math.max

class MicReceiver(private val port: Int = LanMic.DEFAULT_PORT) {
    @Volatile
    private var running = false

    private var thread: Thread? = null
    private var socket: DatagramSocket? = null
    private var track: AudioTrack? = null
    private var trackRate = 0
    private var lastSeq = -1
    private var idleTicks = 0

    fun start(): Int {
        if (running) return port
        val sock = DatagramSocket(null)
        sock.reuseAddress = true
        sock.bind(InetSocketAddress(port))
        sock.soTimeout = 250
        socket = sock
        running = true
        thread = Thread({ loop() }, "lovktv-mic-rx").also { it.start() }
        return port
    }

    fun stop() {
        running = false
        socket?.close()
        socket = null
        thread?.join(500)
        thread = null
        releaseTrack()
    }

    private fun loop() {
        val buf = ByteArray(2048)
        val packet = DatagramPacket(buf, buf.size)
        while (running) {
            try {
                socket?.receive(packet) ?: break
            } catch (_: Exception) {
                idleTicks += 1
                if (idleTicks >= 3) lastSeq = -1
                continue
            }
            idleTicks = 0
            val frame = LanMic.unpack(packet.data, packet.length) ?: continue
            if (lastSeq >= 0 && !LanMic.isNewerSeq(frame.seq, lastSeq)) continue
            lastSeq = frame.seq
            val audio = ensureTrack(frame.sampleRate) ?: continue
            if (frame.pcm.isNotEmpty()) {
                audio.write(frame.pcm, 0, frame.pcm.size)
            }
        }
    }

    @Synchronized
    private fun ensureTrack(sampleRate: Int): AudioTrack? {
        val current = track
        if (current != null && trackRate == sampleRate) return current
        releaseTrack()
        val min = AudioTrack.getMinBufferSize(
            sampleRate,
            AudioFormat.CHANNEL_OUT_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
        )
        if (min <= 0) return null
        val size = max(min, LanMic.frameBytes(sampleRate) * 2)
        val created = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            val builder = AudioTrack.Builder()
                .setAudioAttributes(
                    AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_MEDIA)
                        .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
                        .build(),
                )
                .setAudioFormat(
                    AudioFormat.Builder()
                        .setSampleRate(sampleRate)
                        .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                        .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                        .build(),
                )
                .setBufferSizeInBytes(size)
                .setTransferMode(AudioTrack.MODE_STREAM)
            if (Build.VERSION.SDK_INT >= 26) {
                builder.setPerformanceMode(AudioTrack.PERFORMANCE_MODE_LOW_LATENCY)
            }
            builder.build()
        } else {
            @Suppress("DEPRECATION")
            AudioTrack(
                android.media.AudioManager.STREAM_MUSIC,
                sampleRate,
                AudioFormat.CHANNEL_OUT_MONO,
                AudioFormat.ENCODING_PCM_16BIT,
                size,
                AudioTrack.MODE_STREAM,
            )
        }
        created.play()
        track = created
        trackRate = sampleRate
        return created
    }

    @Synchronized
    private fun releaseTrack() {
        try {
            track?.stop()
        } catch (_: Exception) {
        }
        track?.release()
        track = null
        trackRate = 0
    }
}
