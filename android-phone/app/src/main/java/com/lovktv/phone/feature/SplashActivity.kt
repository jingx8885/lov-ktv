package com.lovktv.phone.feature

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper

/** Product branding screen shown briefly before the phone desk opens. */
class SplashActivity : Activity() {
    private val main = Handler(Looper.getMainLooper())
    private var finished = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(com.lovktv.phone.R.layout.activity_splash)
        main.postDelayed({ goDesk() }, SPLASH_MS)
    }

    private fun goDesk() {
        if (finished) return
        finished = true
        startActivity(Intent(this, DeskActivity::class.java))
        finish()
        @Suppress("DEPRECATION")
        overridePendingTransition(android.R.anim.fade_in, android.R.anim.fade_out)
    }

    override fun onDestroy() {
        finished = true
        main.removeCallbacksAndMessages(null)
        super.onDestroy()
    }

    companion object {
        private const val SPLASH_MS = 1600L
    }
}
