package com.lovktv.phone

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.media.AudioFormat
import android.media.AudioRecord
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

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val host = intent?.getStringExtra(EXTRA_HOST).orEmpty()
        val port = intent?.getIntExtra(EXTRA_PORT, 0) ?: 0
        val rate = intent?.getIntExtra(EXTRA_RATE, LanMic.SAMPLE_RATE) ?: LanMic.SAMPLE_RATE
        if (host.isBlank() || port !in 1..65535) {
            stopSelf()
            return START_NOT_STICKY
        }
        ensureChannel()
        startAsForeground()
        if (!running) {
            running = true
            live = true
            thread = Thread({ sendLoop(host, port, rate) }, "lovktv-mic-tx").also { it.start() }
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
        thread?.join(400)
        thread = null
        super.onDestroy()
    }

    private fun sendLoop(host: String, port: Int, requestedRate: Int) {
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
        val address = InetAddress.getByName(host)
        try {
            while (running) {
                val got = rec.read(pcm, 0, frame)
                if (got <= 0) continue
                val packetBytes = LanMic.pack(seq and 0xFFFF, rate, pcm, 0, got)
                seq += 1
                sock.send(DatagramPacket(packetBytes, packetBytes.size, address, port))
            }
        } catch (_: Exception) {
        } finally {
            running = false
            live = false
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

    private fun startAsForeground() {
        val notification = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Notification.Builder(this, CHANNEL_ID)
                .setContentTitle(getString(R.string.app_name))
                .setContentText("低延时麦发送中")
                .setSmallIcon(android.R.drawable.ic_btn_speak_now)
                .setOngoing(true)
                .build()
        } else {
            @Suppress("DEPRECATION")
            Notification.Builder(this)
                .setContentTitle(getString(R.string.app_name))
                .setContentText("低延时麦发送中")
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
        private const val CHANNEL_ID = "lovktv-mic"
        private const val NOTIFICATION_ID = 18787

        @Volatile
        var live: Boolean = false
            private set

        val running: Boolean get() = live

        fun start(context: Context, host: String, port: Int, rate: Int) {
            val app = context.applicationContext
            val intent = Intent(app, MicService::class.java)
                .putExtra(EXTRA_HOST, host)
                .putExtra(EXTRA_PORT, port)
                .putExtra(EXTRA_RATE, rate)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                app.startForegroundService(intent)
            } else {
                app.startService(intent)
            }
        }

        fun stop(context: Context) {
            val app = context.applicationContext
            app.stopService(Intent(app, MicService::class.java))
        }
    }
}
