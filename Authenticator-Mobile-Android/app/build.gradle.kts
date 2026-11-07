import org.gradle.api.tasks.Sync

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
    id("com.chaquo.python")
}

val desktopProject = layout.projectDirectory.dir("../../Authenticator-PC-Python")
val generatedPython = layout.buildDirectory.dir("generated/sharedPython")

val syncSharedPython by tasks.registering(Sync::class) {
    into(generatedPython)
    from(desktopProject.dir("domain")) { into("domain") }
    from(desktopProject.dir("application")) { into("application") }
    from(desktopProject.dir("infrastructure")) {
        into("infrastructure")
        include(
            "__init__.py",
            "backup_codec.py",
            "crypto.py",
            "errors.py",
            "key_protection.py",
            "secure_storage.py",
            "vault_repository.py",
            "vault_store.py",
        )
    }
}

android {
    namespace = "com.authenticatordesktop.mobile"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.authenticatordesktop.mobile"
        minSdk = 26
        targetSdk = 35
        versionCode = 38
        versionName = "1.4.25"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        ndk { abiFilters += "arm64-v8a" }
    }

    buildFeatures { compose = true }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    packaging { resources.excludes += "/META-INF/{AL2.0,LGPL2.1}" }
    testOptions { unitTests.isIncludeAndroidResources = true }
    lint { disable += "ChromeOsAbiSupport" }
}

chaquopy {
    defaultConfig {
        version = "3.11"
        val configuredPython = providers.environmentVariable("AUTHENTICATOR_PYTHON311").orNull
        if (configuredPython.isNullOrBlank()) buildPython("py", "-3.11") else buildPython(configuredPython)
        pip { install("cryptography==42.0.8") }
        pyc { src = true; pip = true; stdlib = true }
    }
    sourceSets.getByName("main") {
        srcDir("src/main/python")
        srcDir(generatedPython)
    }
}

tasks.matching { it.name.contains("Python") && it.name != "syncSharedPython" }.configureEach {
    dependsOn(syncSharedPython)
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2025.02.00")
    implementation(composeBom)
    androidTestImplementation(composeBom)

    implementation("androidx.activity:activity-compose:1.10.1")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.7")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.7")
    implementation("androidx.camera:camera-camera2:1.4.1")
    implementation("androidx.camera:camera-lifecycle:1.4.1")
    implementation("androidx.camera:camera-view:1.4.1")
    implementation("com.google.mlkit:barcode-scanning:17.3.0")
    implementation("com.google.zxing:core:3.5.3")
    implementation("com.github.mwiede:jsch:2.28.7")

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20240303")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    androidTestImplementation("androidx.compose.ui:ui-test-junit4")
    debugImplementation("androidx.compose.ui:ui-tooling")
    debugImplementation("androidx.compose.ui:ui-test-manifest")
}
