// SPDX-License-Identifier: GPL-3.0-or-later
plugins {
    // AGP 9 has Kotlin built in: the org.jetbrains.kotlin.android plugin is not applied any more.
    id("com.android.application") version "9.4.1" apply false
    id("org.jetbrains.kotlin.plugin.compose") version "2.4.20" apply false
}
