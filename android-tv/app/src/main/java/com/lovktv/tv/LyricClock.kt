/** Karaoke audio is the master clock. Native MV follows it. */
object LyricClock {
    const val SYNC_SLACK_MS = 800
    const val SEEK_COOLDOWN_MS = 2000
    const val CLOCK_WARMUP_MS = 200

    fun videoLeadMs(mtvDurationMs: Int, karaokeDurationMs: Int): Int {
        val extra = mtvDurationMs - karaokeDurationMs
        return if (extra in 1500..30_000) extra else 0
    }

    fun videoSeekMs(audioMs: Int, mtvDurationMs: Int, karaokeDurationMs: Int): Int {
        return (audioMs + videoLeadMs(mtvDurationMs, karaokeDurationMs)).coerceAtLeast(0)
    }

    fun shouldSeek(nativeMs: Int, targetMs: Int, lastSeekAt: Long, now: Long, playing: Boolean = true): Boolean {
        if (!playing) return false
        if (nativeMs < CLOCK_WARMUP_MS && targetMs > 1000) return false
        if (kotlin.math.abs(nativeMs - targetMs) <= SYNC_SLACK_MS) return false
        if (now - lastSeekAt < SEEK_COOLDOWN_MS) return false
        return true
    }
}
