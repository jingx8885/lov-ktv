package com.lovktv.tv

import android.annotation.SuppressLint
import android.os.Bundle
import android.webkit.WebChromeClient
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.EditText
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity

class MainActivity : AppCompatActivity() {
    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val prefs = getSharedPreferences("lovktv", MODE_PRIVATE)
        val saved = prefs.getString("server", "http://10.0.2.2:8787/tv.html")
        val input = EditText(this).apply { setText(saved) }
        AlertDialog.Builder(this)
            .setTitle("lov-ktv 服务器")
            .setView(input)
            .setPositiveButton("打开") { _, _ ->
                val url = input.text.toString().ifBlank { saved }
                prefs.edit().putString("server", url).apply()
                val view = WebView(this)
                view.settings.javaScriptEnabled = true
                view.settings.mediaPlaybackRequiresUserGesture = false
                view.webViewClient = WebViewClient()
                view.webChromeClient = WebChromeClient()
                setContentView(view)
                view.loadUrl(url ?: "http://10.0.2.2:8787/tv.html")
            }
            .setCancelable(false)
            .show()
    }
}
