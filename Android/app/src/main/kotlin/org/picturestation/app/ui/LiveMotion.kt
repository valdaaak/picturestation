// SPDX-License-Identifier: GPL-3.0-or-later
package org.picturestation.app.ui

import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.unit.dp
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import org.picturestation.app.data.LiveCache
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory
import androidx.media3.ui.AspectRatioFrameLayout
import androidx.media3.ui.PlayerView
import org.picturestation.app.AppViewModel

/** The motion of a Live Photo, played once over its photo; [onDone] when it ended or failed.
 *  Invisible until the first frame is drawn, so the photo stays until the video really runs. */
@Composable
fun LiveMotion(vm: AppViewModel, liveId: String, muted: Boolean, crop: Boolean, modifier: Modifier = Modifier, onDone: () -> Unit) {
    val ctx = LocalContext.current
    var shown by remember(liveId) { mutableStateOf(false) }
    val player = remember(liveId) {
        // through the clip cache: a prefetched motion starts at once (LiveCache)
        val sources = DefaultMediaSourceFactory(LiveCache.factory(ctx, vm.api))
        ExoPlayer.Builder(ctx).setMediaSourceFactory(sources).build().apply {
            volume = if (muted) 0f else 1f
            setMediaItem(LiveCache.mediaItem(vm.api, liveId))
            playWhenReady = true
            prepare()
        }
    }
    DisposableEffect(player) {
        val listener = object : Player.Listener {
            override fun onRenderedFirstFrame() { shown = true }
            override fun onPlaybackStateChanged(state: Int) { if (state == Player.STATE_ENDED) onDone() }
            override fun onPlayerError(error: PlaybackException) { onDone() }
        }
        player.addListener(listener)
        onDispose { player.removeListener(listener); player.release() }
    }
    AndroidView(
        factory = {
            (android.view.LayoutInflater.from(it).inflate(org.picturestation.app.R.layout.live_player, null) as PlayerView).apply {
                resizeMode = if (crop) AspectRatioFrameLayout.RESIZE_MODE_ZOOM else AspectRatioFrameLayout.RESIZE_MODE_FIT
                this.player = player
            }
        },
        modifier = modifier.fillMaxSize().alpha(if (shown) 1f else 0f),
    )
}

/** The small LIVE mark of a Live Photo. */
@Composable
fun LiveBadge(modifier: Modifier = Modifier, size: TextUnit = 11.sp) {
    Text(
        "LIVE", color = Color.White, fontSize = size,
        modifier = modifier.padding(6.dp).background(Color(0x99000000), RoundedCornerShape(6.dp)).padding(horizontal = 6.dp, vertical = 2.dp),
    )
}
