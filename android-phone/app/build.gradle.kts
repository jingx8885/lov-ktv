plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.lovktv.phone"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.lovktv.phone"
        minSdk = 24
        targetSdk = 34
        versionCode = 1
        versionName = "1.0"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("debug")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    lint {
        // The phone shell intentionally embeds the remote web desk and keeps a
        // branded splash; its LAN HTTP bridge also requires cleartext traffic.
        disable += setOf(
            "CustomSplashScreen",
            "InsecureBaseConfiguration",
            "LockedOrientationActivity",
            "Overdraw",
            "RtlEnabled",
            "SetJavaScriptEnabled",
            "UnusedResources",
        )
    }
}

dependencies {
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("com.journeyapps:zxing-android-embedded:4.3.0")
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20240303")
}
