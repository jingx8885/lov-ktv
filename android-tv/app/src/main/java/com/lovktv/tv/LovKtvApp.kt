package com.lovktv.tv

import android.app.Application

class LovKtvApp : Application() {
    override fun onCreate() {
        super.onCreate()
        if (Prefs.serverUrl(this).isNotBlank()) {
            HostService.ensureStarted(this)
        }
    }
}
