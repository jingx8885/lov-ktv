package com.lovktv.phone.platform

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.Shader
import android.graphics.Typeface
import android.media.MediaMetadata
import android.media.session.MediaSession
import android.media.session.PlaybackState
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.util.LruCache
import com.lovktv.phone.R
import com.lovktv.phone.feature.DeskActivity
import com.lovktv.phone.media.PlaybackService
import java.util.concurrent.TimeUnit
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject

/**
 * The notification shade companion for the phone WebView.
 *
 * The web shell tells us which page is visible and which song is current.  We
 * deliberately keep the action ids semantic (rather than depending on DOM
 * labels) so translations and styling changes do not break the shade controls.
 *
 * The card doubles as the lock-screen / screen-off media control: the media
 * session stays active and public so the system keyguard, ambient display and
 * Android 13+ media carousel all render the same artwork and transport keys.
 */
class PhoneNotificationController(private val context: Context) {
    private val manager = context.getSystemService(NotificationManager::class.java)
    private val mediaSession = MediaSession(context, "lov-ktv-phone")
    private val http = OkHttpClient.Builder()
        .connectTimeout(5, TimeUnit.SECONDS)
        .readTimeout(8, TimeUnit.SECONDS)
        .build()
    private val artCache = LruCache<String, Bitmap>(24)
    private val artPending = java.util.Collections.synchronizedSet(mutableSetOf<String>())
    private val artFailed = java.util.Collections.synchronizedSet(mutableSetOf<String>())
    private val mainHandler = Handler(Looper.getMainLooper())

    private var lastPayload = ""
    private var lastMeta = ""
    private var lastPage = "desk"
    private var lastTitle = ""
    private var lastArtist = ""
    private var lastPlaying = false
    private var lastCover = ""
    private var lastLyric = ""
    private var lastLyricTrans = ""
    private var lastLyricNext = ""
    private var lastDurationMs = 0L
    private var lastPositionMs = 0L

    /** DeskActivity wires this to the WebView so the lock-screen seek bar works. */
    var onSeekTo: ((Long) -> Unit)? = null

    init {
        if (Build.VERSION.SDK_INT >= 26) {
            // v2 channel: the v1 channel was IMPORTANCE_LOW which some ROMs hide
            // from the lock screen entirely.  DEFAULT with sound/vibration off
            // keeps the card silent while letting the keyguard show it.
            manager.createNotificationChannel(
                NotificationChannel(CHANNEL_ID, context.getString(R.string.notification_channel), NotificationManager.IMPORTANCE_DEFAULT).apply {
                    description = context.getString(R.string.notification_channel_desc)
                    setShowBadge(false)
                    setSound(null, null)
                    enableVibration(false)
                    lockscreenVisibility = Notification.VISIBILITY_PUBLIC
                },
            )
            runCatching { manager.deleteNotificationChannel(LEGACY_CHANNEL_ID) }
        }
        mediaSession.setCallback(object : MediaSession.Callback() {
            override fun onPlay() = DeskActivity.dispatchNotificationAction(context, if (lastPage == "player") ACTION_PLAYER_PLAY else ACTION_DESK_PAUSE)
            override fun onPause() = DeskActivity.dispatchNotificationAction(context, if (lastPage == "player") ACTION_PLAYER_PLAY else ACTION_DESK_PAUSE)
            override fun onSkipToNext() = DeskActivity.dispatchNotificationAction(context, if (lastPage == "player") ACTION_PLAYER_NEXT else ACTION_DESK_SKIP)
            override fun onSeekTo(pos: Long) {
                onSeekTo?.invoke(pos)
            }
        })
        @Suppress("DEPRECATION")
        mediaSession.setFlags(MediaSession.FLAG_HANDLES_MEDIA_BUTTONS or MediaSession.FLAG_HANDLES_TRANSPORT_CONTROLS)
        // Lets the keyguard / media carousel open the app by tapping the card.
        mediaSession.setSessionActivity(openIntent("desk"))
        mediaSession.isActive = true
    }

    fun update(payloadJson: String) {
        // Notification work must never take the player down: remote views and
        // bitmaps can throw on some ROMs, so the whole refresh is guarded.
        runCatching { updateInternal(payloadJson) }
    }

    private fun updateInternal(payloadJson: String) {
        val payload = runCatching { JSONObject(payloadJson) }.getOrNull() ?: return
        lastPage = payload.optString("page").ifBlank { "desk" }
        lastTitle = payload.optString("title").trim()
        lastArtist = payload.optString("artist").trim()
        lastPlaying = payload.optBoolean("playing", false)
        lastCover = payload.optString("cover").trim()
        val lyricRaw = payload.optString("lyric").trim()
        val split = lyricRaw.split(" / ", limit = 2)
        lastLyric = split[0].trim()
        lastLyricTrans = if (split.size > 1) split[1].trim() else ""
        lastLyricNext = payload.optString("lyricNext").trim()
        lastDurationMs = (payload.optDouble("duration", 0.0) * 1000).toLong().coerceAtLeast(0L)
        lastPositionMs = (payload.optDouble("position", 0.0) * 1000).toLong().coerceIn(0L, if (lastDurationMs > 0) lastDurationMs else Long.MAX_VALUE)

        // Session state is cheap to refresh: it drives the lock-screen card and
        // the seek bar, so update it on every heartbeat even when the shade
        // notification itself does not need a rebuild.
        val seekable = lastPage == "player" && lastDurationMs > 0
        var sessionActions = PlaybackState.ACTION_PLAY or PlaybackState.ACTION_PAUSE or PlaybackState.ACTION_SKIP_TO_NEXT
        if (seekable) sessionActions = sessionActions or PlaybackState.ACTION_SEEK_TO
        mediaSession.setPlaybackState(
            PlaybackState.Builder()
                .setState(if (lastPlaying) PlaybackState.STATE_PLAYING else PlaybackState.STATE_PAUSED, lastPositionMs, 1f)
                .setActions(sessionActions)
                .build(),
        )
        post()
    }

    private fun post() {
        val listening = lastPage == "player"
        val label = if (listening) context.getString(R.string.notification_listening) else context.getString(R.string.notification_karaoke)
        val songTitle = lastTitle.ifBlank { context.getString(if (listening) R.string.notification_idle_listen else R.string.notification_idle_karaoke) }
        val art = artworkFor(songTitle)

        // Lyrics take the second text slot on the card and the lock screen;
        // the artist name stays attached to the album field so it still shows
        // where the system renders a third line.
        val subLine = lastLyric.ifBlank { lastArtist }
        val albumLine = if (lastLyric.isNotBlank() && lastArtist.isNotBlank()) "$lastArtist · $label" else label
        val metaKey = listOf(songTitle, subLine, albumLine, lastDurationMs, art != null).joinToString("\u0000")
        if (metaKey != lastMeta) {
            lastMeta = metaKey
            mediaSession.setMetadata(
                MediaMetadata.Builder()
                    .putString(MediaMetadata.METADATA_KEY_TITLE, songTitle)
                    .putString(MediaMetadata.METADATA_KEY_ARTIST, subLine)
                    .putString(MediaMetadata.METADATA_KEY_ALBUM, albumLine)
                    .putLong(MediaMetadata.METADATA_KEY_DURATION, lastDurationMs)
                    .apply { if (art != null) putBitmap(MediaMetadata.METADATA_KEY_ALBUM_ART, art) }
                    .build(),
            )
        }

        val key = listOf(lastPage, lastTitle, lastArtist, lastLyric, lastLyricNext, lastPlaying, lastCover, lastDurationMs, art != null).joinToString("\u0000")
        if (key == lastPayload) return
        lastPayload = key

        val builder = if (Build.VERSION.SDK_INT >= 26) {
            // Foreground-service posts crash (BadNotificationForForegroundException)
            // when the notification carries no channel on O+, and regular posts are
            // silently dropped. Bind the channel we create in init.
            Notification.Builder(context, CHANNEL_ID)
        } else {
            @Suppress("DEPRECATION")
            Notification.Builder(context)
        }
            .setSmallIcon(R.drawable.ic_notif_small)
            .setContentTitle(songTitle)
            .setContentText(if (lastLyric.isNotBlank()) lastLyric else if (lastArtist.isBlank()) label else lastArtist)
            .setSubText(if (lastLyric.isNotBlank() && lastArtist.isNotBlank()) lastArtist else label)
            .setContentIntent(openIntent(lastPage))
            .setCategory(Notification.CATEGORY_TRANSPORT)
            .setVisibility(Notification.VISIBILITY_PUBLIC)
            .setColor(context.getColor(R.color.accent))
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setShowWhen(false)
        if (Build.VERSION.SDK_INT >= 26) {
            builder.setColorized(true)
        }
        if (art != null) builder.setLargeIcon(art)

        // Compact order is play-pause, next, then the page's signature action;
        // the fourth button only shows when the card is expanded.
        if (listening) {
            builder
                .addAction(action(if (lastPlaying) R.drawable.ic_notif_pause else R.drawable.ic_notif_play, if (lastPlaying) context.getString(R.string.notification_pause) else context.getString(R.string.notification_play), ACTION_PLAYER_PLAY))
                .addAction(action(R.drawable.ic_notif_next, context.getString(R.string.notification_next), ACTION_PLAYER_NEXT))
                .addAction(action(R.drawable.ic_notif_vocal, context.getString(R.string.notification_vocal), ACTION_PLAYER_VOCAL))
                .addAction(action(R.drawable.ic_notif_queue, context.getString(R.string.notification_to_karaoke), ACTION_TO_DESK))
        } else {
            builder
                .addAction(action(if (lastPlaying) R.drawable.ic_notif_pause else R.drawable.ic_notif_play, if (lastPlaying) context.getString(R.string.notification_pause) else context.getString(R.string.notification_play), ACTION_DESK_PAUSE))
                .addAction(action(R.drawable.ic_notif_next, context.getString(R.string.notification_skip), ACTION_DESK_SKIP))
                .addAction(action(R.drawable.ic_notif_mic, context.getString(R.string.notification_mic), ACTION_DESK_MIC))
                .addAction(action(R.drawable.ic_notif_search, context.getString(R.string.notification_search), ACTION_SEARCH))
        }
        if (Build.VERSION.SDK_INT >= 21) {
            builder.setStyle(
                Notification.MediaStyle()
                    .setMediaSession(mediaSession.sessionToken)
                    .setShowActionsInCompactView(0, 1, 2),
            )
        }
        postNotification(builder, songTitle, label)
    }

    /**
     * Custom RemoteViews crash SystemUI-side too (bad attr, bitmap over the
     * binder transaction limit, ROM quirks).  If either path throws we rebuild
     * the plain media card so listening never takes the app down.
     */
    private fun postNotification(builder: Notification.Builder, songTitle: String, label: String) {
        var notification = runCatching { builder.build() }.getOrElse {
            rebuildStandard(songTitle, label)
        }
        try {
            // While a track is actually playing the shade entry is owned by the
            // mediaPlayback foreground service, which also keeps the WebView
            // (and the JS that advances tracks) alive in the background.
            PlaybackService.sync(context, lastPlaying, notification)
            manager.notify(NOTIFICATION_ID, notification)
        } catch (_: RuntimeException) {
            notification = rebuildStandard(songTitle, label)
            runCatching {
                PlaybackService.sync(context, lastPlaying, notification)
                manager.notify(NOTIFICATION_ID, notification)
            }
        }
    }

    /** The pre-custom-layout media card: known-safe on every ROM we shipped. */
    private fun rebuildStandard(songTitle: String, label: String): Notification {
        val builder = if (Build.VERSION.SDK_INT >= 26) {
            Notification.Builder(context, CHANNEL_ID)
        } else {
            @Suppress("DEPRECATION")
            Notification.Builder(context)
        }
            .setSmallIcon(R.drawable.ic_notif_small)
            .setContentTitle(songTitle)
            .setContentText(if (lastLyric.isNotBlank()) lastLyric else if (lastArtist.isBlank()) label else lastArtist)
            .setSubText(if (lastLyric.isNotBlank() && lastArtist.isNotBlank()) lastArtist else label)
            .setContentIntent(openIntent(lastPage))
            .setCategory(Notification.CATEGORY_TRANSPORT)
            .setVisibility(Notification.VISIBILITY_PUBLIC)
            .setColor(context.getColor(R.color.accent))
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setShowWhen(false)
        val playIcon = if (lastPlaying) R.drawable.ic_notif_pause else R.drawable.ic_notif_play
        val playLabel = if (lastPlaying) context.getString(R.string.notification_pause) else context.getString(R.string.notification_play)
        if (lastPage == "player") {
            builder
                .addAction(action(playIcon, playLabel, ACTION_PLAYER_PLAY))
                .addAction(action(R.drawable.ic_notif_next, context.getString(R.string.notification_next), ACTION_PLAYER_NEXT))
                .addAction(action(R.drawable.ic_notif_vocal, context.getString(R.string.notification_vocal), ACTION_PLAYER_VOCAL))
                .addAction(action(R.drawable.ic_notif_queue, context.getString(R.string.notification_to_karaoke), ACTION_TO_DESK))
        } else {
            builder
                .addAction(action(playIcon, playLabel, ACTION_DESK_PAUSE))
                .addAction(action(R.drawable.ic_notif_next, context.getString(R.string.notification_skip), ACTION_DESK_SKIP))
                .addAction(action(R.drawable.ic_notif_mic, context.getString(R.string.notification_mic), ACTION_DESK_MIC))
                .addAction(action(R.drawable.ic_notif_search, context.getString(R.string.notification_search), ACTION_SEARCH))
        }
        if (Build.VERSION.SDK_INT >= 21) {
            builder.setStyle(
                Notification.MediaStyle()
                    .setMediaSession(mediaSession.sessionToken)
                    .setShowActionsInCompactView(0, 1, 2),
            )
        }
        return builder.build()
    }

    private fun artworkFor(title: String): Bitmap? {
        if (lastCover.isBlank()) return fallbackArt(title)
        val cached = artCache.get(lastCover)
        if (cached != null) return cached
        if (!artFailed.contains(lastCover) && artPending.add(lastCover)) {
            val url = lastCover
            Thread({
                val bmp = fetchCover(url)
                artPending.remove(url)
                if (bmp != null) {
                    artCache.put(url, bmp)
                    // Repost so the card picks the real cover up; the payload
                    // key now differs because art is non-null.
                    mainHandler.post { post() }
                } else {
                    artFailed.add(url)
                }
            }, "lovktv-cover").start()
        }
        return fallbackArt(title)
    }

    private fun fetchCover(url: String): Bitmap? {
        return runCatching {
            http.newCall(Request.Builder().url(url).build()).execute().use { res ->
                if (!res.isSuccessful) return@use null
                val bytes = res.body?.bytes() ?: return@use null
                val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
                BitmapFactory.decodeByteArray(bytes, 0, bytes.size, bounds)
                if (bounds.outWidth <= 0 || bounds.outHeight <= 0) return@use null
                var sample = 1
                while (bounds.outWidth / sample > 1024 || bounds.outHeight / sample > 1024) sample *= 2
                val raw = BitmapFactory.decodeByteArray(bytes, 0, bytes.size, BitmapFactory.Options().apply { inSampleSize = sample })
                    ?: return@use null
                square(raw)
            }
        }.getOrNull()
    }

    /** Center-crop to a square so the media card and keyguard art stay uniform. */
    private fun square(src: Bitmap): Bitmap {
        val side = minOf(src.width, src.height)
        val out = Bitmap.createBitmap(ART_SIZE, ART_SIZE, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(out)
        val left = (src.width - side) / 2f
        val top = (src.height - side) / 2f
        val paint = Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG)
        canvas.drawBitmap(src, android.graphics.Rect(left.toInt(), top.toInt(), (left + side).toInt(), (top + side).toInt()), android.graphics.Rect(0, 0, ART_SIZE, ART_SIZE), paint)
        return out
    }

    /**
     * Branded placeholder that mirrors the web side's art.js tile: a stable
     * two-tone gradient picked by the title hash plus its first glyph, so a
     * cover-less song still looks intentional on the lock screen.
     */
    private fun fallbackArt(title: String): Bitmap {
        val key = "fallback:$title"
        artCache.get(key)?.let { return it }
        val pair = PALETTE[(fnv(title) and 0x7fffffff) % PALETTE.size]
        val out = Bitmap.createBitmap(ART_SIZE, ART_SIZE, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(out)
        canvas.drawRect(
            0f, 0f, ART_SIZE.toFloat(), ART_SIZE.toFloat(),
            Paint(Paint.ANTI_ALIAS_FLAG).apply {
                shader = LinearGradient(0f, 0f, ART_SIZE.toFloat(), ART_SIZE.toFloat(), pair.first, pair.second, Shader.TileMode.CLAMP)
            },
        )
        val glyph = title.firstOrNull { it.isLetterOrDigit() }?.uppercase() ?: "♪"
        val text = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.argb(0xE0, 255, 255, 255)
            textSize = ART_SIZE * 0.42f
            typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
            textAlign = Paint.Align.CENTER
        }
        canvas.drawText(glyph, ART_SIZE / 2f, ART_SIZE / 2f - (text.ascent() + text.descent()) / 2f, text)
        artCache.put(key, out)
        return out
    }

    private fun fnv(text: String): Int {
        var h = 0x811C9DC5.toInt()
        for (ch in text) {
            h = h xor ch.code
            h *= 16777619
        }
        return h
    }

    private fun openIntent(page: String): PendingIntent {
        val intent = Intent(context, DeskActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
            putExtra(DeskActivity.EXTRA_NOTIFICATION_PAGE, page)
        }
        return PendingIntent.getActivity(context, REQUEST_OPEN, intent, pendingFlags())
    }

    fun close() {
        runCatching { PlaybackService.stop(context) }
        mainHandler.removeCallbacksAndMessages(null)
        runCatching { manager.cancel(NOTIFICATION_ID) }
        runCatching { mediaSession.isActive = false }
        runCatching { mediaSession.release() }
    }

    private fun actionPending(action: String): PendingIntent {
        val intent = Intent(context, NotificationActionReceiver::class.java)
            .putExtra(EXTRA_ACTION, action)
            .putExtra(EXTRA_PAGE, lastPage)
        return PendingIntent.getBroadcast(context, action.hashCode(), intent, pendingFlags())
    }

    private fun action(icon: Int, title: String, action: String): Notification.Action {
        return Notification.Action.Builder(icon, title, actionPending(action)).build()
    }

    private fun pendingFlags(): Int {
        var flags = PendingIntent.FLAG_UPDATE_CURRENT
        if (Build.VERSION.SDK_INT >= 23) flags = flags or PendingIntent.FLAG_IMMUTABLE
        return flags
    }

    companion object {
        const val EXTRA_ACTION = "lovktv.notification.action"
        const val EXTRA_PAGE = "lovktv.notification.page"
        const val ACTION_SEARCH = "search"
        const val ACTION_TO_DESK = "desk"
        const val ACTION_DESK_PAUSE = "desk_pause"
        const val ACTION_DESK_SKIP = "desk_skip"
        const val ACTION_DESK_MIC = "desk_mic"
        const val ACTION_PLAYER_PLAY = "player_play"
        const val ACTION_PLAYER_NEXT = "player_next"
        const val ACTION_PLAYER_VOCAL = "player_vocal"
        private const val CHANNEL_ID = "lovktv_playback_v2"
        private const val LEGACY_CHANNEL_ID = "lovktv_playback"
        private const val NOTIFICATION_ID = 4101
        private const val REQUEST_OPEN = 4102
        private const val ART_SIZE = 256

        /** Same curated gradient pairs as frontend/public/shared/ui/js/art.js. */
        private val PALETTE = listOf(
            0xFFFF6B8F.toInt() to 0xFF6E1634.toInt(),
            0xFF9A8CFF.toInt() to 0xFF2B2170.toInt(),
            0xFF5CC8FF.toInt() to 0xFF123C66.toInt(),
            0xFFFFB36B.toInt() to 0xFF7A2E1A.toInt(),
            0xFF4FE0B5.toInt() to 0xFF0F4A46.toInt(),
            0xFFFF86DC.toInt() to 0xFF4B1A6B.toInt(),
            0xFFFFD56B.toInt() to 0xFF6B4512.toInt(),
            0xFF7CB8FF.toInt() to 0xFF3A1F6B.toInt(),
        )
    }
}

class NotificationActionReceiver : android.content.BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val action = intent.getStringExtra(PhoneNotificationController.EXTRA_ACTION).orEmpty()
        val page = intent.getStringExtra(PhoneNotificationController.EXTRA_PAGE).orEmpty()
        if (action.isNotBlank()) DeskActivity.dispatchNotificationAction(context, action, page)
    }
}
