package com.lovktv.tv

import android.media.MediaPlayer
import org.junit.Assert.assertEquals
import org.junit.Test

class SilentMtvTest {
    @Test
    fun audioTrackTypeIsDistinctFromVideo() {
        assertEquals(MediaPlayer.TrackInfo.MEDIA_TRACK_TYPE_AUDIO, 2)
        assertEquals(MediaPlayer.TrackInfo.MEDIA_TRACK_TYPE_VIDEO, 1)
    }
}
