// SPDX-License-Identifier: GPL-3.0-or-later
package org.picturestation.app

import android.content.pm.PackageManager
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.key
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import coil.Coil
import coil.ImageLoader
import org.picturestation.app.ui.BrowseScreen
import org.picturestation.app.ui.Navy
import org.picturestation.app.ui.Paper
import org.picturestation.app.ui.PairScreen
import org.picturestation.app.ui.PicturestationTheme
import org.picturestation.app.ui.SettingsScreen
import org.picturestation.app.ui.SetupScreen
import org.picturestation.app.ui.StartScreen
import org.picturestation.app.ui.ViewerScreen
import org.picturestation.app.ui.admin.AccessScreen
import org.picturestation.app.ui.admin.AdminScreen
import org.picturestation.app.ui.admin.AlbumAccessScreen

/** One activity for phones, tablets and Android TV; the screens come from the view model's stack. */
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val vm: AppViewModel by viewModels()
        vm.isTv = packageManager.hasSystemFeature(PackageManager.FEATURE_LEANBACK)
        // thumbnails through the app's OkHttp client, so that the session travels in a header
        Coil.setImageLoader(ImageLoader.Builder(this).okHttpClient(vm.api.client).build())
        setContent { PicturestationTheme { Root(vm) } }
    }
}

@Composable
fun Root(vm: AppViewModel) {
    val ctx = LocalContext.current
    val screen = vm.current
    BackHandler(enabled = vm.stack.size > 1) { vm.pop() }
    LaunchedEffect(vm.message) { vm.message?.let { Toast.makeText(ctx, it, Toast.LENGTH_SHORT).show(); vm.message = null } }
    Surface(modifier = Modifier.fillMaxSize(), color = Navy, contentColor = Paper) {
        when (screen) {
            is Screen.Setup -> SetupScreen(vm)
            is Screen.Pair -> PairScreen(vm)
            is Screen.Start -> StartScreen(vm)
            is Screen.Settings -> SettingsScreen(vm)
            // key(): every album gets its own composition, so its effects and scroll state start afresh
            is Screen.Browse -> key(screen.state) {
                BrowseScreen(
                    vm, screen.state,
                    onOpenAlbum = {
                        vm.push(Screen.Browse(BrowseState(when (it.type) {
                            "album" -> Where(album = it)
                            // a tile of the Collections: People, Tags, Places, or one country of the places
                            "coll" -> Where(coll = it.name, cc = it.cc, country = it.country)
                            else -> Where(group = it)   // a tag, a person, a place or a smart album
                        })))
                    },
                    onOpenCollections = { vm.push(Screen.Browse(BrowseState(Where(coll = "root")))) },
                    onOpenLatest = { vm.push(Screen.Browse(BrowseState(Where(latest = true)))) },
                    onOpenMedia = { i, slideshow -> vm.push(Screen.Viewer(screen.state, i, slideshow)) },
                    onSettings = { vm.push(Screen.Settings) },
                    onBack = { vm.pop() },
                )
            }
            is Screen.Viewer -> key(screen) { ViewerScreen(vm, screen.state, screen.start, screen.slideshow, onBack = { vm.pop() }) }
            is Screen.Admin -> AdminScreen(vm)
            is Screen.Access -> key(screen) { AccessScreen(vm, screen) }
            is Screen.AlbumAccess -> key(screen) { AlbumAccessScreen(vm, screen.path) }
        }
    }
}
