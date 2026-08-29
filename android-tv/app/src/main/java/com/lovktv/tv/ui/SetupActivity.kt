package com.lovktv.tv.ui

import com.lovktv.tv.R

import com.lovktv.tv.feature.host.HostService
import com.lovktv.tv.platform.Prefs
import android.content.Intent
import android.os.Bundle
import android.app.Activity
import android.widget.Button
import android.widget.EditText

class SetupActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val force = intent.getBooleanExtra(EXTRA_FORCE, false)
        val saved = Prefs.serverUrl(this)
        if (saved.isNotBlank() && !force) {
            openTv()
            return
        }
        setContentView(R.layout.activity_setup)
        val input = findViewById<EditText>(R.id.server)
        input.setText(saved.ifBlank { Prefs.DEFAULT_SERVER })
        input.requestFocus()
        findViewById<Button>(R.id.open).setOnClickListener {
            Prefs.saveServer(this, input.text.toString())
            HostService.ensureStarted(this)
            openTv()
        }
    }

    private fun openTv() {
        HostService.ensureStarted(this)
        startActivity(Intent(this, TvActivity::class.java))
        finish()
    }

    companion object {
        const val EXTRA_FORCE = "force_setup"
    }
}
