// SPDX-License-Identifier: GPL-3.0-or-later
package org.picturestation.app.ui.admin

import android.content.Intent
import android.os.Build
import android.widget.Toast
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch
import org.picturestation.app.AppViewModel
import org.picturestation.app.R
import org.picturestation.app.data.baseName
import org.picturestation.app.data.shareUrl
import org.picturestation.app.ui.Amber
import org.picturestation.app.ui.Paper

/** A link to an album, a photo or a video for people without an account (the web's Share button): validity,
 *  downloading, a note; then the link to copy or send. */
@Composable
fun ShareDialog(vm: AppViewModel, path: String, kind: String, onDone: () -> Unit) {
    var days by remember { mutableStateOf("30") }
    var allowDownload by remember { mutableStateOf(false) }
    var note by remember { mutableStateOf("") }
    var token by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()
    val options = listOf("0" to stringResource(R.string.share_no_limit), "7" to stringResource(R.string.share_7d),
        "30" to stringResource(R.string.share_30d), "90" to stringResource(R.string.share_90d), "365" to stringResource(R.string.share_1y))
    val what = if (kind == "album") stringResource(R.string.share_album_fmt, baseName(path)) else baseName(path)
    AlertDialog(
        onDismissRequest = onDone,
        title = { Text(stringResource(R.string.share_fmt, what)) },
        text = {
            Column(modifier = Modifier.verticalScroll(rememberScrollState())) {
                MutedText(stringResource(if (kind == "album") R.string.share_help_album else R.string.share_help_item))
                Spacer(Modifier.height(8.dp))
                val t = token
                if (t == null) {
                    OptionPicker(stringResource(R.string.share_valid), options, days) { days = it }
                    CheckRow(stringResource(R.string.share_allow_dl), allowDownload, { allowDownload = it })
                    FormField(stringResource(R.string.share_note), note, { note = it })
                } else LinkBox(shareUrl(vm.api.server, t))
            }
        },
        confirmButton = {
            if (token == null) TextButton(onClick = {
                scope.launch {
                    val t = vm.adminFetch { shareCreate(path, days.toInt(), allowDownload, note.trim()) }
                    if (t != null) { token = t; vm.admin?.shares = null }   // the Shares tab loads the list again
                }
            }) { Text(stringResource(R.string.share_create)) }
            else TextButton(onClick = onDone) { Text(stringResource(R.string.done)) }
        },
        dismissButton = { if (token == null) TextButton(onClick = onDone) { Text(stringResource(R.string.cancel)) } },
    )
}

/** The link with Copy and Send (the Android share sheet). */
@Composable
fun LinkBox(url: String) {
    val ctx = LocalContext.current
    val clipboard = LocalClipboardManager.current
    val copied = stringResource(R.string.link_copied)
    Column(modifier = Modifier.fillMaxWidth()) {
        Text(url, color = Paper, fontSize = 13.sp)
        Row(verticalAlignment = Alignment.CenterVertically) {
            TextButton(onClick = {
                clipboard.setText(AnnotatedString(url))
                if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) Toast.makeText(ctx, copied, Toast.LENGTH_SHORT).show()
            }) { Text(stringResource(R.string.copy), color = Amber) }
            TextButton(onClick = {
                val send = Intent(Intent.ACTION_SEND).apply { type = "text/plain"; putExtra(Intent.EXTRA_TEXT, url) }
                ctx.startActivity(Intent.createChooser(send, null))
            }) { Text(stringResource(R.string.send), color = Amber) }
        }
    }
}
