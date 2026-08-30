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

val generatedAssets = layout.buildDirectory.dir("generated/assets")
val frontendDist = rootProject.projectDir.resolve("../frontend/frontend-dist")
val buildFrontendDist = tasks.register<Exec>("buildFrontendDist") {
    workingDir(rootProject.projectDir.parentFile)
    commandLine("python", "scripts/build-frontend-dist.py", "--source", "frontend/public", "--output", "frontend/frontend-dist")
}
// Sync removes files deleted from frontend-dist so stale assets cannot leak into an APK.
val copyWebAssets = tasks.register<Sync>("copyWebAssets") {
    dependsOn(buildFrontendDist)
    from(frontendDist)
    into(generatedAssets.map { it.dir("web") })
    exclude("**/.DS_Store")
}

android {
    namespace = "com.lovktv.tv"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.lovktv.tv"
        minSdk = 21
        targetSdk = 34
        versionCode = appVersionCode
        versionName = appVersionName
    }

    buildTypes {
        release {
            isMinifyEnabled = false
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
        // TV-only resources and local-network WebView behavior are intentional.
        disable += setOf(
            "Autofill",
            "CustomSplashScreen",
            "GradleDependency",
            "IconLauncherShape",
            "IconLocation",
            "InsecureBaseConfiguration",
            // targetSdk 34 is intentional while the TV compatibility matrix is validated.
            "OldTargetApi",
            "Overdraw",
            "UnusedAttribute",
            "UnusedResources",
        )
    }

    sourceSets.getByName("main").assets.srcDir(generatedAssets)

    packaging {
        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
            excludes += "/META-INF/INDEX.LIST"
            excludes += "/META-INF/io.netty.versions.properties"
        }
    }
}

tasks.named("preBuild").configure { dependsOn(copyWebAssets) }

dependencies {
    implementation("androidx.leanback:leanback:1.0.0")
    implementation("io.ktor:ktor-server-cio:2.3.12")
    implementation("io.ktor:ktor-server-websockets:2.3.12")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.7.3")
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20240303")
}
