package com.lovktv.phone.feature

import com.lovktv.phone.R

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.widget.Button
import android.widget.Toast
import com.google.zxing.BarcodeFormat
import com.google.zxing.ResultPoint
import com.journeyapps.barcodescanner.BarcodeCallback
import com.journeyapps.barcodescanner.BarcodeResult
import com.journeyapps.barcodescanner.DecoratedBarcodeView
import com.journeyapps.barcodescanner.DefaultDecoderFactory

class ScanActivity : Activity() {
    private lateinit var barcodeView: DecoratedBarcodeView
    private var handled = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_scan)
        barcodeView = findViewById(R.id.barcode)
        barcodeView.barcodeView.decoderFactory = DefaultDecoderFactory(listOf(BarcodeFormat.QR_CODE))
        barcodeView.setStatusText(getString(R.string.scan_hint))
        barcodeView.decodeContinuous(object : BarcodeCallback {
            override fun barcodeResult(result: BarcodeResult?) {
                val text = result?.text?.trim().orEmpty()
                if (handled || text.isEmpty()) return
                handled = true
                barcodeView.pause()
                setResult(RESULT_OK, Intent().putExtra(EXTRA_TEXT, text))
                finish()
            }

            override fun possibleResultPoints(resultPoints: MutableList<ResultPoint>?) = Unit
        })
        findViewById<Button>(R.id.cancel).setOnClickListener {
            setResult(RESULT_CANCELED)
            finish()
        }
        if (checkSelfPermission(Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.CAMERA), REQ_CAMERA)
        }
    }

    override fun onResume() {
        super.onResume()
        if (checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
            barcodeView.resume()
        }
    }

    override fun onPause() {
        barcodeView.pause()
        super.onPause()
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        if (requestCode != REQ_CAMERA) return
        if (grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED) {
            barcodeView.resume()
        } else {
            Toast.makeText(this, R.string.scan_need_camera, Toast.LENGTH_SHORT).show()
            setResult(RESULT_CANCELED)
            finish()
        }
    }

    companion object {
        const val EXTRA_TEXT = "scan_text"
        const val REQ = 41
        private const val REQ_CAMERA = 42

        @Suppress("DEPRECATION")
        fun start(activity: Activity) {
            activity.startActivityForResult(Intent(activity, ScanActivity::class.java), REQ)
        }
    }
}
