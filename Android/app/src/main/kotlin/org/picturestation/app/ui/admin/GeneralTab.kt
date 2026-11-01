// SPDX-License-Identifier: GPL-3.0-or-later
package org.picturestation.app.ui.admin

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import org.picturestation.app.AdminState
import org.picturestation.app.AppViewModel
import org.picturestation.app.R
import org.picturestation.app.data.AdminInfo
import org.picturestation.app.data.FLAG_KEYS
import org.picturestation.app.data.json

/** The gallery's name, order, language and the twelve restrictions (the web's General tab). */
@Composable
fun GeneralTab(vm: AppViewModel, st: AdminState, info: AdminInfo) {
    val s = info.settings
    var title by remember(info) { mutableStateOf(s.title) }
    var order by remember(info) { mutableStateOf(s.rootAlbumOrder) }
    var language by remember(info) { mutableStateOf(s.language) }
    val flags = remember(info) { mutableStateMapOf<String, Boolean>().also { m -> FLAG_KEYS.forEach { m[it] = s.flags[it] == true } } }
    var error by remember { mutableStateOf<String?>(null) }
    val okSaved = stringResource(R.string.saved)
    Column(modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).imePadding().padding(16.dp)) {
        AdminCard {
            FormField(stringResource(R.string.gen_title), title, { title = it })
            Spacer(Modifier.height(8.dp))
            OptionPicker(stringResource(R.string.gen_root_order),
                listOf("desc" to stringResource(R.string.gen_order_desc), "asc" to stringResource(R.string.gen_order_asc)), order) { order = it }
            Spacer(Modifier.height(8.dp))
            OptionPicker(stringResource(R.string.gen_language),
                listOf("auto" to stringResource(R.string.lang_auto), "en" to "English", "sk" to "Slovenčina"), language) { language = it }
            Spacer(Modifier.height(12.dp))
            SectionTitle(stringResource(R.string.gen_restrictions))
            FLAG_KEYS.forEach { k -> CheckRow(flagLabel(k), flags[k] == true, { flags[k] = it }) }
            MutedText(stringResource(R.string.gen_dl_note))
            Spacer(Modifier.height(8.dp))
            Button(
                onClick = {
                    error = null
                    val body = json("title" to title.trim(), "root_album_order" to order, "language" to language,
                        *FLAG_KEYS.map { it to (flags[it] == true) }.toTypedArray())
                    vm.adminRun("settings", body, ok = okSaved) { e -> if (e == null) vm.setGalleryTitle(title.trim()) else error = e }
                },
                enabled = !st.busy, modifier = Modifier.fillMaxWidth(),
            ) { Text(stringResource(R.string.save)) }
            InlineError(error)
        }
        Spacer(Modifier.height(12.dp))
        MutedText(stringResource(R.string.gen_version, info.version))
    }
}

@Composable
private fun flagLabel(key: String): String = stringResource(when (key) {
    "allow_download_user" -> R.string.flag_allow_download_user
    "allow_download_guest" -> R.string.flag_allow_download_guest
    "hide_gps" -> R.string.flag_hide_gps
    "hide_detail_user" -> R.string.flag_hide_detail_user
    "hide_detail_guest" -> R.string.flag_hide_detail_guest
    "disable_timeline" -> R.string.flag_disable_timeline
    "disable_search" -> R.string.flag_disable_search
    "allow_comment_user" -> R.string.flag_allow_comment_user
    "allow_comment_guest" -> R.string.flag_allow_comment_guest
    "root_files_public" -> R.string.flag_root_files_public
    "people_for_guest" -> R.string.flag_people_for_guest
    else -> R.string.flag_live_photos
})
