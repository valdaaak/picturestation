// SPDX-License-Identifier: GPL-3.0-or-later
package org.picturestation.app.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

val Navy = Color(0xFF0F172A)
val NavyLight = Color(0xFF1E293B)
val Paper = Color(0xFFF6F7FA)
val Amber = Color(0xFFF5B942)
val Muted = Color(0xFF9AA3AD)
val Focus = Color(0xFF4DA3FF)
val Danger = Color(0xFFE5654B)   // disabled, excluded, delete

private val scheme = darkColorScheme(
    primary = Amber, onPrimary = Navy,
    background = Navy, onBackground = Paper,
    surface = NavyLight, onSurface = Paper,
    secondary = Focus,
)

@Composable
fun PicturestationTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = scheme, content = content)
}
