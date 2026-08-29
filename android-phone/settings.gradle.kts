pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
        // Keep the mirror as a fallback for networks where Maven Central is unavailable.
        maven { url = uri("https://maven.aliyun.com/repository/google") }
        maven { url = uri("https://maven.aliyun.com/repository/public") }
        maven { url = uri("https://maven.aliyun.com/repository/gradle-plugin") }
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
        // Keep the mirror as a fallback for networks where Maven Central is unavailable.
        maven { url = uri("https://maven.aliyun.com/repository/google") }
        maven { url = uri("https://maven.aliyun.com/repository/public") }
    }
}

rootProject.name = "lov-ktv-phone"
include(":app")
