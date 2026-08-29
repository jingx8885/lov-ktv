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
        // These checks describe intentional product choices: the phone shell is a
        // local-network WebView, keeps a branded splash, and ships shared strings
        // used by the web bridge. Keep actionable API/permission checks enabled.
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
