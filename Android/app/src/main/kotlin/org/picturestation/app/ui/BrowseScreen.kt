// SPDX-License-Identifier: GPL-3.0-or-later
package org.picturestation.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.rememberLazyGridState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Schedule
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import org.picturestation.app.AppViewModel
import org.picturestation.app.BrowseState
import org.picturestation.app.R
import org.picturestation.app.data.Item

private const val SPECIAL_LATEST = "latest"

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun BrowseScreen(
    vm: AppViewModel, st: BrowseState,
    onOpenAlbum: (Item) -> Unit, onOpenLatest: () -> Unit,
    onOpenMedia: (Int, Boolean) -> Unit, onSettings: () -> Unit, onBack: () -> Unit,
) {
    val sessionEnded = stringResource(R.string.session_ended)
    val passwordNote = stringResource(R.string.album_password)
    val failed = stringResource(R.string.load_failed)
    val network = stringResource(R.string.network_retry)
    val isRoot = st.where.album == null && !st.where.latest
    val specials = if (isRoot && vm.showLatest) 1 else 0
    val grid = rememberLazyGridState(initialFirstVisibleItemIndex = st.firstVisible + specials)

    LaunchedEffect(Unit) { if (st.items.isEmpty()) vm.load(st, sessionEnded, passwordNote, failed, network) }
    LaunchedEffect(grid) {
        snapshotFlow { grid.layoutInfo.visibleItemsInfo.lastOrNull()?.index ?: 0 }.collect { last ->
            if (last >= st.items.size + specials - 40) vm.load(st, sessionEnded, passwordNote, failed, network)
            st.firstVisible = maxOf(0, grid.firstVisibleItemIndex - specials)
        }
    }

    val title = when {
        st.where.latest -> stringResource(R.string.latest_photos)
        st.where.album != null -> st.where.album.title
        else -> vm.title.ifEmpty { "Picturestation" }
    }
    val count = if (st.total == 1) stringResource(R.string.items_one, 1) else stringResource(R.string.items_many, st.total)
    val mediaCount = st.items.count { it.isMedia }

    Scaffold(
        containerColor = Navy,
        topBar = {
            TopAppBar(
                title = { Column { Text(title, maxLines = 1, overflow = TextOverflow.Ellipsis); Text(count, style = MaterialTheme.typography.labelMedium, color = Muted) } },
                navigationIcon = { if (!isRoot) IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, stringResource(R.string.back)) } },
                actions = {
                    if (mediaCount > 0) IconButton(onClick = { onOpenMedia(0, true) }) { Icon(Icons.Filled.PlayArrow, stringResource(R.string.slideshow)) }
                    if (isRoot) IconButton(onClick = onSettings) { Icon(Icons.Filled.Settings, stringResource(R.string.settings)) }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = Navy, titleContentColor = Paper),
            )
        },
    ) { pad ->
        val cell = if (vm.isTv) 200.dp else 112.dp
        Box(modifier = Modifier.fillMaxSize().padding(pad)) {
            LazyVerticalGrid(
                columns = GridCells.Adaptive(cell), state = grid,
                contentPadding = PaddingValues(if (vm.isTv) 32.dp else 4.dp),
                horizontalArrangement = Arrangement.spacedBy(4.dp), verticalArrangement = Arrangement.spacedBy(4.dp),
            ) {
                if (specials == 1) item(key = SPECIAL_LATEST) {
                    Tile(tv = vm.isTv, onClick = onOpenLatest) {
                        Column(modifier = Modifier.fillMaxSize().background(Color(0xFF263040)),
                            horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
                            Icon(Icons.Filled.Schedule, null, modifier = Modifier.size(40.dp), tint = Paper)
                            Text(stringResource(R.string.latest_photos), modifier = Modifier.padding(top = 8.dp), color = Paper)
                        }
                    }
                }
                items(st.items.size, key = { st.items[it].id }) { i ->
                    val it = st.items[i]
                    Tile(tv = vm.isTv, onClick = {
                        if (it.type == "album") onOpenAlbum(it) else onOpenMedia(st.mediaIndexOf(it), false)
                    }) {
                        if (it.hasThumb) AsyncImage(
                            model = vm.api.thumbUrl(it, "small"), contentDescription = it.title,
                            contentScale = ContentScale.Crop, modifier = Modifier.fillMaxSize(),
                        )
                        if (it.type == "album") Text(
                            it.title, maxLines = 1, overflow = TextOverflow.Ellipsis, color = Paper,
                            modifier = Modifier.align(Alignment.BottomStart).fillMaxWidth()
                                .background(Color(0x99000000)).padding(horizontal = 8.dp, vertical = 4.dp),
                        )
                        if (it.type == "video") Text(
                            duration(it.durationMs), color = Paper, style = MaterialTheme.typography.labelSmall,
                            modifier = Modifier.align(Alignment.TopEnd).padding(6.dp)
                                .background(Color(0x99000000), RoundedCornerShape(6.dp)).padding(horizontal = 6.dp, vertical = 2.dp),
                        )
                    }
                }
            }
            st.error?.let { Text(it, color = Muted, modifier = Modifier.align(Alignment.Center).padding(24.dp)) }
            if (!st.loading && st.error == null && st.items.isEmpty() && specials == 0)
                Text(stringResource(R.string.no_photos), color = Muted, modifier = Modifier.align(Alignment.Center))
            if (st.loading && st.items.isEmpty()) CircularProgressIndicator(modifier = Modifier.align(Alignment.Center))
        }
    }
}

/** A square tile; on a TV it shows a focus frame for the D-pad. */
@Composable
private fun Tile(tv: Boolean, onClick: () -> Unit, content: @Composable androidx.compose.foundation.layout.BoxScope.() -> Unit) {
    var focused by remember { mutableStateOf(false) }
    Box(
        modifier = Modifier.aspectRatio(1f).clip(RoundedCornerShape(10.dp)).background(NavyLight)
            .onFocusChanged { focused = it.isFocused }
            .then(if (tv && focused) Modifier.border(4.dp, Focus, RoundedCornerShape(10.dp)) else Modifier)
            .clickable(onClick = onClick),
        content = content,
    )
}

fun duration(ms: Int): String {
    val s = (ms + 500) / 1000
    return if (s <= 0) "video" else "%d:%02d".format(s / 60, s % 60)
}
