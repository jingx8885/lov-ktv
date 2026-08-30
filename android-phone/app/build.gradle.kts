plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

fun lovktvVersion(): Pair<String, Int> {
    var name = "1.0"
    var code = 1
    val file = rootProject.projectDir.resolve("../VERSION")
    if (file.isFile) {
        file.readLines().forEach { line ->
            val parts = line.split("=", limit = 2)
            if (parts.size != 2) return@forEach
            when (parts[0].trim()) {
                "name" -> name = parts[1].trim().ifBlank { name }
                "code" -> code = parts[1].trim().toIntOrNull() ?: code
            }
        }
    }
    return name to code
}

val (appVersionName, appVersionCode) = lovktvVersion()

android {
    namespace = "com.lovktv.phone"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.lovktv.phone"
        minSdk = 24
        targetSdk = 34
        versionCode = appVersionCode
        versionName = appVersionName
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
            // targetSdk 34 is intentional while the app's compatibility matrix is validated.
            "OldTargetApi",
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
