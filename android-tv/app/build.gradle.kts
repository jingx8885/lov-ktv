plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

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
        versionCode = 1
        versionName = "1.0"
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
