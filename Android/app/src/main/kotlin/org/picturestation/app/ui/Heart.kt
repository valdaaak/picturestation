// SPDX-License-Identifier: GPL-3.0-or-later
package org.picturestation.app.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.scale
import androidx.compose.ui.graphics.vector.PathParser
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp

/** The colour of a photo marked as Best Foto (the same on the web and on the LG TV). */
val Heart = Color(0xFFF0566A)

// One outline for every client, drawn on a 24 x 24 grid (web/app.js HEART, LGTV/app/js/app.js HEART)
private const val HEART_PATH =
    "M12 20.4C5.6 15.6 3 12.3 3 8.9 3 6.1 5.1 4 7.8 4c1.7 0 3.2.9 4.2 2.3C13 4.9 14.5 4 16.2 4 18.9 4 21 6.1 21 8.9c0 3.4-2.6 6.7-9 11.5z"

/** The Best Foto heart. state 0: an empty outline; 1: filled; 2: half filled with a dashed outline (a suggestion
 *  that waits for the administrator). `shadow` puts a dark edge behind it, for a badge over a photo. */
@Composable
fun HeartIcon(state: Int, description: String?, modifier: Modifier = Modifier.size(24.dp), shadow: Boolean = false) {
    val path = remember { PathParser().parsePathString(HEART_PATH).toPath() }
    val tint = if (state == 0) Paper else Heart
    Canvas(modifier = if (description != null) modifier.semantics { contentDescription = description } else modifier) {
        scale(size.minDimension / 24f, pivot = Offset.Zero) {
            if (shadow) drawPath(path, Color(0xB3000000), style = Stroke(width = 4.2f, join = StrokeJoin.Round))
            if (state != 0) drawPath(path, tint, alpha = if (state == 2) 0.3f else 1f)
            drawPath(path, tint, style = Stroke(width = 1.8f, join = StrokeJoin.Round,
                pathEffect = if (state == 2) PathEffect.dashPathEffect(floatArrayOf(2.6f, 2.2f)) else null))
        }
    }
}
