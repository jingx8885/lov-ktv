package com.lovktv.phone.media

import com.lovktv.phone.R

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.AudioTrack
import android.media.MediaRecorder
import android.os.Build
import android.os.IBinder
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import kotlin.math.max

class MicService : Service() {
    @Volatile
    private var running = false
    private var thread: Thread? = null
    private var record: AudioRecord? = null
    private var socket: DatagramSocket? = null
    private var iem: AudioTrack? = null
    private var iemRate = 0

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val host = intent?.getStringExtra(EXTRA_HOST).orEmpty().ifBlank { sendHost }
        val port = (intent?.getIntExtra(EXTRA_PORT, 0) ?: 0).takeIf { it in 1..65535 } ?: sendPort
        val rate = intent?.getIntExtra(EXTRA_RATE, LanMic.SAMPLE_RATE) ?: LanMic.SAMPLE_RATE
        if (intent?.hasExtra(EXTRA_SEND) == true) sendEnabled = intent.getBooleanExtra(EXTRA_SEND, sendEnabled)
        if (intent?.hasExtra(EXTRA_IEM) == true) iemEnabled = intent.getBooleanExtra(EXTRA_IEM, iemEnabled)
        if (intent?.hasExtra(EXTRA_GAIN) == true) gainPct = intent.getIntExtra(EXTRA_GAIN, gainPct).coerceIn(0, 100)
        sendHost = host
        sendPort = port
        if (!sendEnabled && !iemEnabled) {
            stopSelf()
            return START_NOT_STICKY
        }
        if (sendEnabled && (host.isBlank() || port !in 1..65535) && !iemEnabled) {
            stopSelf()
            return START_NOT_STICKY
        }
        ensureChannel()
        startAsForeground()
        if (!running) {
            running = true
            live = true
            thread = Thread({ sendLoop(rate) }, "lovktv-mic-tx").also { it.start() }
        }
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        running = false
        live = false
        try {
            record?.stop()
        } catch (_: Exception) {
        }
        record?.release()
        record = null
        socket?.close()
        socket = null
        releaseIem()
        thread?.join(400)
        thread = null
        super.onDestroy()
    }

    private fun sendLoop(requestedRate: Int) {
        val rec = openRecord(requestedRate)
        if (rec == null) {
            running = false
            live = false
            stopSelf()
            return
        }
        record = rec
        val rate = rec.sampleRate
        val frame = LanMic.frameBytes(rate)
        val pcm = ByteArray(frame)
        var seq = 0
        rec.startRecording()
        val sock = DatagramSocket()
        socket = sock
        var dest: InetAddress? = null
        var destKey = ""
        try {
            while (running && (sendEnabled || iemEnabled)) {
                val got = rec.read(pcm, 0, frame)
                if (got <= 0) continue
                NativeMic.scalePcm(pcm, got, gainPct)
                if (iemEnabled) {
                    ensureIem(rate)?.write(pcm, 0, got)
                } else {
                    releaseIem()
                }
                val destHost = sendHost
                val destPort = sendPort
                if (sendEnabled && destHost.isNotBlank() && destPort in 1..65535) {
                    val key = "$destHost:$destPort"
                    if (dest == null || destKey != key) {
                        dest = InetAddress.getByName(destHost)
                        destKey = key
                    }
                    val packetBytes = LanMic.pack(seq and 0xFFFF, rate, pcm, 0, got)
                    seq += 1
                    sock.send(DatagramPacket(packetBytes, packetBytes.size, dest, destPort))
                }
            }
        } catch (_: Exception) {
        } finally {
            running = false
            live = false
            releaseIem()
            stopSelf()
        }
    }

    private fun openRecord(rate: Int): AudioRecord? {
        val sources = listOf(
            MediaRecorder.AudioSource.UNPROCESSED,
            MediaRecorder.AudioSource.VOICE_RECOGNITION,
            MediaRecorder.AudioSource.MIC,
        )
        for (source in sources) {
            val rec = buildRecord(source, rate) ?: continue
            if (rec.state == AudioRecord.STATE_INITIALIZED) return rec
            rec.release()
        }
        return null
    }

    private fun buildRecord(source: Int, rate: Int): AudioRecord? {
        val min = AudioRecord.getMinBufferSize(rate, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        if (min <= 0) return null
        val size = max(min, LanMic.frameBytes(rate) * 4)
        return try {
            AudioRecord.Builder()
                .setAudioSource(source)
                .setAudioFormat(
                    AudioFormat.Builder()
                        .setSampleRate(rate)
                        .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                        .setChannelMask(AudioFormat.CHANNEL_IN_MONO)
                        .build(),
                )
                .setBufferSizeInBytes(size)
                .build()
        } catch (_: Exception) {
            null
        }
    }

    private fun ensureIem(rate: Int): AudioTrack? {
        val existing = iem
        if (existing != null && iemRate == rate) return existing
        releaseIem()
        val min = AudioTrack.getMinBufferSize(rate, AudioFormat.CHANNEL_OUT_MONO, AudioFormat.ENCODING_PCM_16BIT)
        if (min <= 0) return null
        val builder = AudioTrack.Builder()
            .setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_MEDIA)
                    .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
                    .build(),
            )
            .setAudioFormat(
                AudioFormat.Builder()
                    .setSampleRate(rate)
                    .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                    .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                    .build(),
            )
            .setBufferSizeInBytes(max(min, LanMic.frameBytes(rate) * 2))
            .setTransferMode(AudioTrack.MODE_STREAM)
        if (Build.VERSION.SDK_INT >= 26) {
            builder.setPerformanceMode(AudioTrack.PERFORMANCE_MODE_LOW_LATENCY)
        }
        val track = builder.build()
        track.play()
        iem = track
        iemRate = rate
        return track
    }

    private fun releaseIem() {
        try {
            iem?.stop()
        } catch (_: Exception) {
        }
        iem?.release()
        iem = null
        iemRate = 0
    }

    private fun notifyText(): String {
        return when {
            iemEnabled && sendEnabled -> "低延时麦 + 耳返"
            iemEnabled -> "耳返已开"
            else -> "低延时麦发送中"
        }
    }

    private fun startAsForeground() {
        val text = notifyText()
        val notification = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Notification.Builder(this, CHANNEL_ID)
                .setContentTitle(getString(R.string.app_name))
                .setContentText(text)
                .setSmallIcon(android.R.drawable.ic_btn_speak_now)
                .setOngoing(true)
                .build()
        } else {
            @Suppress("DEPRECATION")
            Notification.Builder(this)
                .setContentTitle(getString(R.string.app_name))
                .setContentText(text)
                .setSmallIcon(android.R.drawable.ic_btn_speak_now)
                .setOngoing(true)
                .build()
        }
        if (Build.VERSION.SDK_INT >= 29) {
            startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE)
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
    }

    private fun ensureChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = getSystemService(NotificationManager::class.java) ?: return
        if (manager.getNotificationChannel(CHANNEL_ID) != null) return
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL_ID, getString(R.string.mic_channel), NotificationManager.IMPORTANCE_LOW),
        )
    }

    companion object {
        const val EXTRA_HOST = "host"
        const val EXTRA_PORT = "port"
        const val EXTRA_RATE = "rate"
        const val EXTRA_SEND = "send"
        const val EXTRA_IEM = "iem"
        const val EXTRA_GAIN = "gain"
        private const val CHANNEL_ID = "lovktv-mic"
        private const val NOTIFICATION_ID = 18787

        @Volatile
        var live: Boolean = false
            private set

        @Volatile
        var sendEnabled: Boolean = false
            private set

        @Volatile
        var iemEnabled: Boolean = false
            private set

        @Volatile
        var gainPct: Int = 100
            private set

        @Volatile
        var sendHost: String = ""
            private set

        @Volatile
        var sendPort: Int = 0
            private set

        val running: Boolean get() = live

        fun apply(
            context: Context,
            host: String,
            port: Int,
            rate: Int,
            send: Boolean? = null,
            iem: Boolean? = null,
            gain: Int? = null,
        ) {
            if (send != null) sendEnabled = send
            if (iem != null) iemEnabled = iem
            if (gain != null) gainPct = gain.coerceIn(0, 100)
            sendHost = host
            sendPort = port
            if (!sendEnabled && !iemEnabled) {
                stop(context)
                return
            }
            val app = context.applicationContext
            val intent = Intent(app, MicService::class.java)
                .putExtra(EXTRA_HOST, host)
                .putExtra(EXTRA_PORT, port)
                .putExtra(EXTRA_RATE, rate)
                .putExtra(EXTRA_SEND, sendEnabled)
                .putExtra(EXTRA_IEM, iemEnabled)
                .putExtra(EXTRA_GAIN, gainPct)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                app.startForegroundService(intent)
            } else {
                app.startService(intent)
            }
        }

        fun start(context: Context, host: String, port: Int, rate: Int) {
            apply(context, host, port, rate, send = true)
        }

        fun stop(context: Context) {
            sendEnabled = false
            iemEnabled = false
            val app = context.applicationContext
            app.stopService(Intent(app, MicService::class.java))
        }
    }
}
