// SPDX-License-Identifier: GPL-3.0-or-later
package org.picturestation.app.ui

import android.content.Intent
import android.widget.Toast
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Pause
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Share
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.input.key.type
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.FileProvider
import androidx.compose.foundation.focusable
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.datasource.okhttp.OkHttpDataSource
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory
import androidx.media3.ui.PlayerView
import coil.compose.AsyncImage
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.Request
import org.picturestation.app.AppViewModel
import org.picturestation.app.BrowseState
import org.picturestation.app.R
import org.picturestation.app.data.Item
import org.picturestation.app.data.formatTaken
import java.io.File
import java.util.Locale

@Composable
fun ViewerScreen(vm: AppViewModel, st: BrowseState, start: Int, slideshow: Boolean, onBack: () -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val media by remember { derivedStateOf { st.items.filter { it.isMedia } } }
    if (media.isEmpty()) { onBack(); return }
    val pager = rememberPagerState(initialPage = start.coerceIn(0, media.size - 1)) { media.size }
    var overlay by remember { mutableStateOf(true) }
    var playing by remember { mutableStateOf(slideshow) }
    var videoPaused by remember { mutableStateOf(false) }
    var details by remember { mutableStateOf<Item?>(null) }
    val sessionEnded = stringResource(R.string.session_ended)
    val passwordNote = stringResource(R.string.album_password)
    val failed = stringResource(R.string.load_failed)
    val network = stringResource(R.string.network_retry)
    val slovak = Locale.getDefault().language in listOf("sk", "cs")
    val noDate = stringResource(R.string.no_date)
    val focus = remember { FocusRequester() }

    fun go(delta: Int) {
        if (media.isEmpty()) return
        val n = (pager.currentPage + delta + media.size) % media.size
        scope.launch { pager.animateScrollToPage(n) }
    }

    // the item in view: details, position for the list behind, more items when near the end
    val current = media.getOrNull(pager.currentPage)
    LaunchedEffect(current?.id) {
        details = null
        current ?: return@LaunchedEffect
        st.firstVisible = st.items.indexOf(current).coerceAtLeast(0)
        if (pager.currentPage >= media.size - 8) vm.load(st, sessionEnded, passwordNote, failed, network)
        details = vm.details(current)
    }
    // slideshow of photos; a video advances when it ends
    LaunchedEffect(playing, current?.id) {
        if (playing && current?.type == "photo") { delay(vm.store.interval * 1000L); go(1) }
    }
    // the overlay hides itself a moment after a change
    LaunchedEffect(overlay, current?.id) { if (overlay) { delay(3500); overlay = false } }
    LaunchedEffect(Unit) { if (vm.isTv) focus.requestFocus() }

    Box(
        modifier = Modifier.fillMaxSize().background(Color.Black).focusRequester(focus).focusable()
            .onPreviewKeyEvent { e ->
                if (e.type != KeyEventType.KeyDown) return@onPreviewKeyEvent false
                when (e.key) {
                    Key.DirectionLeft -> { go(-1); true }
                    Key.DirectionRight -> { go(1); true }
                    Key.DirectionCenter, Key.Enter, Key.DirectionUp, Key.DirectionDown -> { overlay = !overlay; true }
                    Key.MediaPlay, Key.MediaPlayPause, Key.ProgramRed -> { playing = !playing; overlay = true; true }
                    Key.MediaPause, Key.MediaStop, Key.ProgramGreen -> { playing = false; videoPaused = true; overlay = true; true }
                    else -> false
                }
            },
    ) {
        HorizontalPager(state = pager, beyondViewportPageCount = 1, key = { media[it].id }, modifier = Modifier.fillMaxSize()) { page ->
            val item = media[page]
            if (item.type == "video") VideoPage(
                vm = vm, item = item, active = page == pager.currentPage, paused = videoPaused,
                onEnded = { if (playing) go(1) }, onTap = { overlay = !overlay },
            ) else ZoomableImage(url = vm.api.thumbUrl(item, "large"), onTap = { overlay = !overlay })
        }

        if (overlay) {
            Row(
                modifier = Modifier.fillMaxWidth().align(Alignment.TopCenter)
                    .background(Brush.verticalGradient(listOf(Color(0xB3000000), Color.Transparent))).statusBarsPadding().padding(4.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, stringResource(R.string.back), tint = Paper) }
                Text("${pager.currentPage + 1} / ${media.size}${if (st.items.size < st.total) "+" else ""}", color = Paper,
                    modifier = Modifier.weight(1f))
                IconButton(onClick = { playing = !playing }) {
                    Icon(if (playing) Icons.Filled.Pause else Icons.Filled.PlayArrow,
                        stringResource(if (playing) R.string.pause else R.string.play), tint = if (playing) Focus else Paper)
                }
                if (!vm.isTv) IconButton(onClick = { current?.let { share(vm, ctx, it) } }) {
                    Icon(Icons.Filled.Share, stringResource(R.string.share), tint = Paper)
                }
            }
            Column(
                modifier = Modifier.fillMaxWidth().align(Alignment.BottomCenter)
                    .background(Brush.verticalGradient(listOf(Color.Transparent, Color(0xCC000000)))).padding(20.dp),
            ) {
                Text(current?.title ?: "", color = Paper, style = MaterialTheme.typography.titleLarge, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text(formatTaken(current?.taken, slovak, noDate), color = Color(0xFFCFD6DE))
                val who = listOfNotNull(details?.people?.takeIf { it.isNotEmpty() }?.joinToString(", "), details?.place)
                if (who.isNotEmpty()) Text(who.joinToString("   ·   "), color = Color(0xFFFFD37A), maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
        } else if (playing) {
            Icon(Icons.Filled.PlayArrow, null, tint = Focus, modifier = Modifier.align(Alignment.TopStart).statusBarsPadding().padding(16.dp))
        }
    }
}

@Composable
private fun ZoomableImage(url: String, onTap: () -> Unit) {
    var scale by remember { mutableStateOf(1f) }
    var offsetX by remember { mutableStateOf(0f) }
    var offsetY by remember { mutableStateOf(0f) }
    var loading by remember { mutableStateOf(true) }
    Box(modifier = Modifier.fillMaxSize()
        .pointerInput(Unit) { detectTapGestures(onTap = { onTap() }, onDoubleTap = { scale = if (scale > 1f) 1f else 2.5f; offsetX = 0f; offsetY = 0f }) }
        .pointerInput(Unit) {
            detectTransformGestures { _, pan, zoom, _ ->
                scale = (scale * zoom).coerceIn(1f, 6f)
                if (scale > 1f) { offsetX += pan.x; offsetY += pan.y } else { offsetX = 0f; offsetY = 0f }
            }
        }) {
        AsyncImage(
            model = url, contentDescription = null, contentScale = ContentScale.Fit,
            onSuccess = { loading = false }, onError = { loading = false },
            modifier = Modifier.fillMaxSize().graphicsLayer(scaleX = scale, scaleY = scale, translationX = offsetX, translationY = offsetY),
        )
        if (loading) CircularProgressIndicator(modifier = Modifier.align(Alignment.Center), color = Paper)
    }
}

@Composable
private fun VideoPage(vm: AppViewModel, item: Item, active: Boolean, paused: Boolean, onEnded: () -> Unit, onTap: () -> Unit) {
    val ctx = LocalContext.current
    val failedText = stringResource(R.string.video_failed)
    val preparing = stringResource(R.string.upright_preparing)
    val player = remember(item.id) {
        // the app's OkHttp client: the session goes in a header, not in the URL
        val sources = DefaultMediaSourceFactory(OkHttpDataSource.Factory(vm.api.client))
        ExoPlayer.Builder(ctx).setMediaSourceFactory(sources).build().apply {
            // players honour the rotation flag; the TV app needs the upright copy, this one does not
            setMediaItem(MediaItem.fromUri(vm.api.videoUrl(item, "web")))
            prepare()
        }
    }
    DisposableEffect(player) {
        val listener = object : Player.Listener {
            override fun onPlaybackStateChanged(state: Int) { if (state == Player.STATE_ENDED) onEnded() }
            override fun onPlayerError(error: PlaybackException) { Toast.makeText(ctx, failedText, Toast.LENGTH_SHORT).show() }
        }
        player.addListener(listener)
        onDispose { player.removeListener(listener); player.release() }
    }
    LaunchedEffect(active, paused) {
        player.playWhenReady = active && !paused
        if (!active) player.seekTo(0)
    }
    Box(modifier = Modifier.fillMaxSize().pointerInput(Unit) { detectTapGestures(onTap = { onTap() }) }) {
        AndroidView(
            factory = { PlayerView(it).apply { useController = false; this.player = player } },
            modifier = Modifier.fillMaxSize(),
        )
    }
}

/** Share the original file through the system share sheet (downloaded to the cache first). */
private fun share(vm: AppViewModel, ctx: android.content.Context, item: Item) {
    val failed = ctx.getString(R.string.load_failed)
    kotlinx.coroutines.GlobalScope.launch(Dispatchers.IO) {
        try {
            val url = if (item.type == "video") vm.api.videoUrl(item, "web") else vm.api.originalUrl(item)
            val resp = vm.api.client.newCall(Request.Builder().url(url).build()).execute()
            resp.use {
                val type = it.header("content-type") ?: ""
                if (!it.isSuccessful || !(type.startsWith("image/") || type.startsWith("video/"))) throw IllegalStateException(type)
                val dir = File(ctx.cacheDir, "share").apply { mkdirs() }
                dir.listFiles()?.forEach { f -> f.delete() }
                // the name comes from the server: keep only a plain file name
                val safe = File(item.name).name.replace(Regex("[^A-Za-z0-9._-]"), "_").trim('.').ifEmpty { "photo" }
                val file = File(dir, safe)
                if (!file.canonicalPath.startsWith(dir.canonicalPath + File.separator)) throw IllegalStateException("name")
                file.outputStream().use { out -> it.body!!.byteStream().copyTo(out) }
                val uri = FileProvider.getUriForFile(ctx, ctx.packageName + ".fileprovider", file)
                val send = Intent(Intent.ACTION_SEND).setType(type).putExtra(Intent.EXTRA_STREAM, uri)
                    .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                withContext(Dispatchers.Main) {
                    ctx.startActivity(Intent.createChooser(send, null).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                }
            }
        } catch (e: Exception) {
            withContext(Dispatchers.Main) { Toast.makeText(ctx, failed, Toast.LENGTH_SHORT).show() }
        }
    }
}
