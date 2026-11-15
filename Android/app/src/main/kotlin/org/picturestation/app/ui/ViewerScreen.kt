// SPDX-License-Identifier: GPL-3.0-or-later
package org.picturestation.app.ui

import android.content.Intent
import android.widget.Toast
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.gestures.calculatePan
import androidx.compose.foundation.gestures.calculateZoom
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.ui.input.pointer.positionChanged
import androidx.compose.foundation.layout.Box
import androidx.compose.material3.TextButton
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
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Share
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import org.picturestation.app.ui.admin.CoverDialog
import org.picturestation.app.ui.admin.ShareDialog
import org.picturestation.app.ui.admin.TagsDialog
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
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
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
    var adminAction by remember { mutableStateOf<String?>(null) }   // share | cover | tags
    var adminMenu by remember { mutableStateOf(false) }
    var liveId by remember { mutableStateOf<String?>(null) }   // item whose Live Photo motion is playing
    var firstPage by remember { mutableStateOf(true) }
    val sessionEnded = stringResource(R.string.session_ended)
    val passwordNote = stringResource(R.string.album_password)
    val failed = stringResource(R.string.load_failed)
    val network = stringResource(R.string.network_retry)
    val slovak = Locale.getDefault().language in listOf("sk", "cs")
    val noDate = stringResource(R.string.no_date)
    val focus = remember { FocusRequester() }

    val bestMsg = mapOf(
        "sent" to stringResource(R.string.best_sent), "back" to stringResource(R.string.best_taken_back),
        "added" to stringResource(R.string.best_added), "removed" to stringResource(R.string.best_removed),
        "admin" to stringResource(R.string.best_admin_only), "many" to stringResource(R.string.best_too_many),
        "failed" to stringResource(R.string.best_failed), "syno" to stringResource(R.string.best_synology_failed),
    )
    var bestBusy by remember { mutableStateOf(false) }
    var okDown by remember { mutableStateOf(false) }   // OK is held (the press began in the viewer)
    var okLong by remember { mutableStateOf(false) }   // ... and it has already acted as a long press

    fun go(delta: Int) {
        if (media.isEmpty()) return
        val n = (pager.currentPage + delta + media.size) % media.size
        scope.launch { pager.animateScrollToPage(n) }
    }

    // the heart: an administrator tags the photo as Best Foto at once, others suggest it for approval
    fun toggleBest(item: Item) {
        overlay = true
        if (bestBusy) return
        fun say(key: String) = Toast.makeText(ctx, bestMsg[key], Toast.LENGTH_SHORT).show()
        if (item.best == 1 && !vm.isAdmin) { say("admin"); return }
        bestBusy = true
        scope.launch {
            try {
                val d = vm.api.setBest(item.id, item.best == 0)
                val now = d.optInt("best")
                val i = st.items.indexOfFirst { it.id == item.id }
                if (i >= 0) st.items[i] = st.items[i].copy(best = now)
                vm.forgetDetails(item.id)
                say(when {
                    d.optString("synology") in listOf("failed", "missing") -> "syno"
                    now == 2 -> "sent"
                    now == 1 -> "added"
                    item.best == 2 -> "back"
                    else -> "removed"
                })
            } catch (e: org.picturestation.app.data.Api.ApiException) {
                say(when (e.code) { 496 -> "admin"; 497 -> "many"; else -> "failed" })
            } finally { bestBusy = false }
        }
    }

    // the item in view: details, position for the list behind, more items when near the end
    val current = media.getOrNull(pager.currentPage)
    LaunchedEffect(current?.id) {
        details = null
        // Live Photo: the motion plays once when the viewer moves to the photo (arrows, swipe, slideshow);
        // the photo opened from the grid only goes full screen (on a TV its motion played in the grid already)
        liveId = if (!firstPage && current?.type == "photo" && current.live != null) current.id else null
        firstPage = false
        current ?: return@LaunchedEffect
        vm.prefetchLive(media, pager.currentPage, reach = 3)
        st.firstVisible = st.items.indexOf(current).coerceAtLeast(0)
        if (pager.currentPage >= media.size - 8) vm.load(st, sessionEnded, passwordNote, failed, network)
        details = vm.details(current)
    }
    // slideshow of photos; a video advances when it ends
    // (a Live Photo: the interval and the zoom start when its motion has played)
    val livePlaying = current != null && liveId == current.id
    LaunchedEffect(playing, current?.id, livePlaying) {
        if (playing && current?.type == "photo" && !livePlaying) { delay(vm.store.interval * 1000L); go(1) }
    }
    // the overlay hides itself a moment after a change
    LaunchedEffect(overlay, current?.id, adminMenu) { if (overlay && !adminMenu) { delay(3500); overlay = false } }
    LaunchedEffect(Unit) { if (vm.isTv) focus.requestFocus() }

    Box(
        modifier = Modifier.fillMaxSize().background(Color.Black).focusRequester(focus).focusable()
            .onPreviewKeyEvent { e ->
                // OK on a TV: a short press (acted on at release) starts or pauses the slideshow, holding it is the heart.
                // A remote without colour buttons (Chromecast) has no other key for it. Only a press that began
                // here counts: the release of the OK that opened the photo from the grid is not ours.
                if (vm.isTv && (e.key == Key.DirectionCenter || e.key == Key.Enter)) {
                    val n = e.nativeKeyEvent
                    if (e.type == KeyEventType.KeyDown) {
                        if (n.repeatCount == 0) { okDown = true; okLong = false }
                        else if (okDown && !okLong && n.eventTime - n.downTime >= 600) {
                            okLong = true
                            media.getOrNull(pager.currentPage)?.let { toggleBest(it) }
                        }
                    } else if (e.type == KeyEventType.KeyUp && okDown) {
                        okDown = false
                        if (!okLong) { playing = !playing; videoPaused = !playing; overlay = true }
                    }
                    return@onPreviewKeyEvent true
                }
                if (e.type != KeyEventType.KeyDown) return@onPreviewKeyEvent false
                when (e.key) {
                    Key.DirectionLeft -> { go(-1); true }
                    Key.DirectionRight -> { go(1); true }
                    Key.DirectionCenter, Key.Enter -> { overlay = !overlay; true }   // a keyboard on a phone or tablet
                    Key.DirectionUp, Key.DirectionDown -> { overlay = !overlay; true }
                    Key.MediaPlay, Key.MediaPlayPause, Key.ProgramRed -> { playing = !playing; overlay = true; true }
                    Key.MediaPause, Key.MediaStop, Key.ProgramGreen -> { playing = false; videoPaused = true; overlay = true; true }
                    // the top bar is out of reach of the arrows on a TV: the yellow button is the heart
                    Key.ProgramYellow -> { media.getOrNull(pager.currentPage)?.let { toggleBest(it) }; true }
                    else -> false
                }
            },
    ) {
        HorizontalPager(state = pager, beyondViewportPageCount = 1, key = { media[it].id }, modifier = Modifier.fillMaxSize()) { page ->
            val item = media[page]
            // a player only for the video on screen: a neighbour (the pager keeps one page each side) shows its
            // thumbnail and downloads nothing; leaving a video releases its player and its decoder at once.
            // Several 1080p HEVC streams at the same time made playback stutter on a Chromecast HD.
            if (item.type == "video" && page == pager.currentPage) VideoPage(
                vm = vm, item = item, active = true, paused = videoPaused,
                onEnded = { if (playing) go(1) }, onTap = { overlay = !overlay },
            ) else if (item.type == "video") ZoomableImage(
                url = vm.api.thumbUrl(item, "large"), onTap = { overlay = !overlay }, active = false,
            ) else Box(modifier = Modifier.fillMaxSize()) {
                val live = item.live
                // the slideshow zoom waits until the motion of a Live Photo has played (the clip is not zoomed)
                ZoomableImage(
                    url = vm.api.thumbUrl(item, "large"), onTap = { overlay = !overlay },
                    active = page == pager.currentPage, kenBurns = vm.isTv && playing && liveId != item.id,
                    durationMs = vm.store.interval * 1000,
                )
                if (live != null && liveId == item.id && page == pager.currentPage)
                    LiveMotion(vm, live, muted = vm.isTv, crop = false) { liveId = null }
            }
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
                // Live Photo: a tap on LIVE plays the motion (again)
                if (current?.type == "photo" && current.live != null) TextButton(onClick = { liveId = null; scope.launch { delay(50); liveId = current.id } }) {
                    Text("LIVE", color = if (liveId == current.id) Focus else Paper)
                }
                if (current != null) IconButton(onClick = { toggleBest(current) }) {
                    HeartIcon(current.best, stringResource(when (current.best) {
                        1 -> R.string.best_on; 2 -> R.string.best_waiting; else -> if (vm.isAdmin) R.string.best_add else R.string.best_suggest
                    }))
                }
                IconButton(onClick = { playing = !playing }) {
                    Icon(if (playing) Icons.Filled.Pause else Icons.Filled.PlayArrow,
                        stringResource(if (playing) R.string.pause else R.string.play), tint = if (playing) Focus else Paper)
                }
                if (!vm.isTv) IconButton(onClick = { current?.let { share(vm, ctx, it) } }) {
                    Icon(Icons.Filled.Share, stringResource(R.string.share), tint = Paper)
                }
                // an administrator's tools for this photo: a link for others, the album's cover, tags
                if (vm.showAdmin && current?.path?.isNotEmpty() == true) {
                    IconButton(onClick = { adminMenu = true }) { Icon(Icons.Filled.MoreVert, stringResource(R.string.more), tint = Paper) }
                    DropdownMenu(expanded = adminMenu, onDismissRequest = { adminMenu = false }) {
                        DropdownMenuItem(text = { Text(stringResource(R.string.menu_share_link)) }, onClick = { adminMenu = false; playing = false; adminAction = "share" })
                        if (current?.type == "photo") DropdownMenuItem(text = { Text(stringResource(R.string.cover_set)) }, onClick = { adminMenu = false; playing = false; adminAction = "cover" })
                        DropdownMenuItem(text = { Text(stringResource(R.string.tags)) }, onClick = { adminMenu = false; playing = false; adminAction = "tags" })
                    }
                }
            }
            Column(
                modifier = Modifier.fillMaxWidth().align(Alignment.BottomCenter)
                    .background(Brush.verticalGradient(listOf(Color.Transparent, Color(0xCC000000)))).padding(20.dp),
            ) {
                val big = vm.isTv
                Text(current?.title ?: "", color = Paper, fontSize = if (big) 28.sp else 16.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text(formatTaken(current?.taken, slovak, noDate), color = Color(0xFFCFD6DE), fontSize = if (big) 22.sp else 13.sp)
                val who = listOfNotNull(details?.people?.takeIf { it.isNotEmpty() }?.joinToString(", "), details?.place)
                if (who.isNotEmpty()) Text(who.joinToString("   ·   "), color = Color(0xFFFFD37A), fontSize = if (big) 22.sp else 13.sp,
                    maxLines = 2, overflow = TextOverflow.Ellipsis)
                if (big) Text(stringResource(R.string.best_hint_tv), color = Muted, fontSize = 16.sp, modifier = Modifier.padding(top = 6.dp))
            }
        } else if (playing) {
            Icon(Icons.Filled.PlayArrow, null, tint = Focus, modifier = Modifier.align(Alignment.TopStart).statusBarsPadding().padding(16.dp))
        }
        current?.let { item ->
            when (adminAction) {
                "share" -> ShareDialog(vm, item.path, item.type, onDone = { adminAction = null })
                "cover" -> CoverDialog(vm, item.path, onDone = { adminAction = null })
                "tags" -> TagsDialog(vm, item, onDone = { adminAction = null; details = null; scope.launch {
                    vm.forgetDetails(item.id); details = vm.details(item)
                    // the tags may have changed Best Foto: the heart follows
                    val d = details; val i = st.items.indexOfFirst { it.id == item.id }
                    if (d != null && i >= 0 && st.items[i].best != d.best) st.items[i] = st.items[i].copy(best = d.best)
                } })
            }
        }
    }
}

/** A photo fitted to the screen, zoomable by pinch and double tap. In a slideshow on a TV (`kenBurns`) it grows
 *  slowly from fitting the screen to filling it, so a portrait photo ends edge to edge; a pause holds the zoom,
 *  the next photo starts fitted again. */
@Composable
private fun ZoomableImage(url: String, onTap: () -> Unit, active: Boolean = true, kenBurns: Boolean = false, durationMs: Int = 8000) {
    var scale by remember { mutableStateOf(1f) }
    var offsetX by remember { mutableStateOf(0f) }
    var offsetY by remember { mutableStateOf(0f) }
    var loading by remember { mutableStateOf(true) }
    var imgSize by remember { mutableStateOf(IntSize.Zero) }
    var boxSize by remember { mutableStateOf(IntSize.Zero) }
    val grow = remember { Animatable(1f) }
    // how much the fitted photo has to grow to cover the screen (1 = it already does)
    val coverScale = if (imgSize.width > 0 && imgSize.height > 0 && boxSize.width > 0 && boxSize.height > 0) {
        val fit = minOf(boxSize.width.toFloat() / imgSize.width, boxSize.height.toFloat() / imgSize.height)
        val cover = maxOf(boxSize.width.toFloat() / imgSize.width, boxSize.height.toFloat() / imgSize.height)
        cover / fit
    } else 1f
    LaunchedEffect(active) { if (!active) grow.snapTo(1f) }
    LaunchedEffect(kenBurns, active, coverScale) {
        if (kenBurns && active && coverScale > 1.02f && grow.value < coverScale) {
            val remaining = (durationMs * (coverScale - grow.value) / (coverScale - 1f)).toInt()
            grow.animateTo(coverScale, tween(remaining, easing = LinearEasing))
        }
    }
    Box(modifier = Modifier.fillMaxSize().onSizeChanged { boxSize = it }
        .pointerInput(Unit) { detectTapGestures(onTap = { onTap() }, onDoubleTap = { scale = if (scale > 1f) 1f else 2.5f; offsetX = 0f; offsetY = 0f }) }
        .pointerInput(Unit) {
            // pinch zooms; a one-finger drag is ours only while zoomed in, otherwise the pager gets it
            awaitEachGesture {
                awaitFirstDown(requireUnconsumed = false)
                do {
                    val event = awaitPointerEvent()
                    val fingers = event.changes.count { it.pressed }
                    if (fingers > 1 || scale > 1f) {
                        scale = (scale * event.calculateZoom()).coerceIn(1f, 6f)
                        val pan = event.calculatePan()
                        if (scale > 1f) { offsetX += pan.x; offsetY += pan.y } else { offsetX = 0f; offsetY = 0f }
                        event.changes.forEach { if (it.positionChanged()) it.consume() }
                    }
                } while (event.changes.any { it.pressed })
            }
        }) {
        AsyncImage(
            model = url, contentDescription = null, contentScale = ContentScale.Fit,
            onSuccess = { loading = false; imgSize = IntSize(it.result.drawable.intrinsicWidth, it.result.drawable.intrinsicHeight) },
            onError = { loading = false },
            modifier = Modifier.fillMaxSize().graphicsLayer(
                scaleX = scale * grow.value, scaleY = scale * grow.value, translationX = offsetX, translationY = offsetY),
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
