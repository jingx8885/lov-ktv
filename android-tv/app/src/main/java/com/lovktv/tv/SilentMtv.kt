package com.lovktv.tv

import android.media.AudioAttributes
import android.media.MediaPlayer
import android.view.SurfaceHolder
import android.view.SurfaceView
import android.view.View

/**
 * H.264 MV picture on a hardware SurfaceView. Hisense/Android 9 VideoView.setVolume(0,0) often fails,
 * so this player drops audio tracks and remutes after start.
 */
class SilentMtv(private val surface: SurfaceView) : SurfaceHolder.Callback {
    @Volatile
    var url: String = ""
        private set

    @Volatile
    var prepared: Boolean = false
        private set

    private var player: MediaPlayer? = null
    private var surfaceReady: Boolean = false
    private var pendingUrl: String = ""

    init {
        surface.holder.addCallback(this)
        surface.isFocusable = false
        surface.isFocusableInTouchMode = false
        surface.setZOrderMediaOverlay(false)
    }

    override fun surfaceCreated(holder: SurfaceHolder) {
        surfaceReady = true
        player?.setDisplay(holder)
        val next = pendingUrl
        if (next.isNotBlank() && (player == null || url != next || !prepared)) {
            play(next)
        }
    }

    override fun surfaceChanged(holder: SurfaceHolder, format: Int, width: Int, height: Int) = Unit

    override fun surfaceDestroyed(holder: SurfaceHolder) {
        surfaceReady = false
        try {
            player?.setDisplay(null)
        } catch (_: Exception) {
        }
    }

    fun play(path: String) {
        val next = path.trim()
        if (next.isBlank()) {
            stop()
            return
        }
        if (!surfaceReady) {
            pendingUrl = next
            surface.visibility = View.VISIBLE
            return
        }
        if (next == url && player != null && (prepared || isPlaying())) {
            remute()
            if (!isPlaying()) startMuted()
            return
        }
        pendingUrl = next
        releasePlayer()
        url = next
        surface.visibility = View.VISIBLE
        val nextPlayer = MediaPlayer()
        player = nextPlayer
        try {
            nextPlayer.setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_MEDIA)
                    .setContentType(AudioAttributes.CONTENT_TYPE_MOVIE)
                    .build(),
            )
            nextPlayer.setVolume(0f, 0f)
            nextPlayer.isLooping = false
            nextPlayer.setOnPreparedListener { ready ->
                if (player !== ready) return@setOnPreparedListener
                prepared = true
                ready.setDisplay(surface.holder)
                mute(ready)
                startMuted()
            }
            nextPlayer.setOnErrorListener { _, what, extra ->
                android.util.Log.e("lovktv-mtv", "MediaPlayer error what=$what extra=$extra url=$url")
                prepared = false
                surface.visibility = View.GONE
                true
            }
            nextPlayer.setOnCompletionListener {
                prepared = false
            }
            nextPlayer.setDataSource(next)
            nextPlayer.prepareAsync()
        } catch (exc: Exception) {
            android.util.Log.e("lovktv-mtv", "setDataSource failed: ${exc.message}")
            releasePlayer()
            surface.visibility = View.GONE
        }
    }

    fun stop() {
        pendingUrl = ""
        url = ""
        prepared = false
        releasePlayer()
        surface.visibility = View.GONE
    }

    fun pause() {
        try {
            if (player?.isPlaying == true) player?.pause()
        } catch (_: Exception) {
        }
    }

    fun resume() {
        if (prepared && url.isNotBlank() && !isPlaying()) startMuted()
    }

    fun seek(ms: Int) {
        if (!prepared || ms < 0) return
        try {
            player?.seekTo(ms)
            remute()
        } catch (_: Exception) {
        }
    }

    fun positionMs(): Int {
        return try {
            if (prepared) player?.currentPosition ?: 0 else 0
        } catch (_: Exception) {
            0
        }
    }

    fun durationMs(): Int {
        return try {
            if (prepared) (player?.duration ?: 0).coerceAtLeast(0) else 0
        } catch (_: Exception) {
            0
        }
    }

    fun isPlaying(): Boolean {
        return try {
            player?.isPlaying == true
        } catch (_: Exception) {
            false
        }
    }

    private fun startMuted() {
        val active = player ?: return
        try {
            mute(active)
            active.start()
            mute(active)
            remute()
            surface.post { remute() }
            surface.postDelayed({ remute() }, 80)
            surface.postDelayed({ remute() }, 300)
        } catch (exc: Exception) {
            android.util.Log.e("lovktv-mtv", "start failed: ${exc.message}")
        }
    }

    private fun remute() {
        val active = player ?: return
        mute(active)
    }

    private fun releasePlayer() {
        val old = player
        player = null
        prepared = false
        if (old == null) return
        try {
            old.setOnPreparedListener(null)
            old.setOnErrorListener(null)
            old.setOnCompletionListener(null)
            old.setDisplay(null)
            old.stop()
        } catch (_: Exception) {
        }
        try {
            old.reset()
        } catch (_: Exception) {
        }
        try {
            old.release()
        } catch (_: Exception) {
        }
    }

    companion object {
        fun mute(player: MediaPlayer) {
            try {
                player.setVolume(0f, 0f)
            } catch (_: Exception) {
            }
            dropAudioTracks(player)
        }

        fun dropAudioTracks(player: MediaPlayer): Int {
            var dropped = 0
            try {
                val tracks = player.trackInfo ?: return 0
                for (i in tracks.indices) {
                    if (tracks[i].trackType != MediaPlayer.TrackInfo.MEDIA_TRACK_TYPE_AUDIO) continue
                    try {
                        player.deselectTrack(i)
                        dropped += 1
                    } catch (_: Exception) {
                    }
                }
            } catch (_: Exception) {
            }
            return dropped
        }
    }
}
