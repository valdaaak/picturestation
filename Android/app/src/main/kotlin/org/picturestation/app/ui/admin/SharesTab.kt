// SPDX-License-Identifier: GPL-3.0-or-later
package org.picturestation.app.ui.admin

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import org.picturestation.app.AdminState
import org.picturestation.app.AdminTab
import org.picturestation.app.AppViewModel
import org.picturestation.app.R
import org.picturestation.app.data.Share
import org.picturestation.app.data.fmtDay
import org.picturestation.app.data.json
import org.picturestation.app.data.shareUrl
import org.picturestation.app.ui.Danger

/** The share links of the gallery: what they open, how long they last, and a way to cancel them. */
@Composable
fun SharesTab(vm: AppViewModel, st: AdminState) {
    var revoking by remember { mutableStateOf<Share?>(null) }
    val okRevoked = stringResource(R.string.share_revoked)
    LaunchedEffect(st.shares == null) { vm.adminLoadTab(AdminTab.SHARES) }
    val shares = st.shares
    LazyColumn(modifier = Modifier.fillMaxSize(), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        when {
            shares == null -> item { Spinner() }
            shares.isEmpty() -> item { MutedText(stringResource(R.string.shares_none)) }
            else -> items(shares, key = { it.token }) { s -> ShareCard(vm, s) { revoking = s } }
        }
    }
    revoking?.let { s ->
        ConfirmDialog(text = stringResource(R.string.share_revoke_q), confirmLabel = stringResource(R.string.share_revoke),
            onConfirm = { vm.adminRun("share_delete", json("token" to s.token), ok = okRevoked) }, onDismiss = { revoking = null })
    }
}

@Composable
private fun ShareCard(vm: AppViewModel, s: Share, onRevoke: () -> Unit) {
    AdminCard {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(s.path, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
            Tag(stringResource(when (s.kind) { "album" -> R.string.kind_album; "video" -> R.string.kind_video; else -> R.string.kind_photo }),
                if (s.expired) TagKind.BAD else TagKind.ACCENT)
        }
        val validity = when {
            s.expires == null -> stringResource(R.string.share_no_limit)
            s.expired -> stringResource(R.string.share_expired, fmtDay(s.expires))
            else -> stringResource(R.string.share_valid_until, fmtDay(s.expires))
        }
        MutedText(validity + " · " + stringResource(R.string.share_created_by, s.createdBy, fmtDay(s.created))
            + (if (s.allowDownload) " · " + stringResource(R.string.share_dl_allowed) else ""))
        if (s.note.isNotEmpty()) MutedText(s.note)
        if (!s.expired) LinkBox(shareUrl(vm.api.server, s.token))
        Spacer(Modifier.width(0.dp))
        TextButton(onClick = onRevoke) { Text(stringResource(R.string.share_revoke), color = Danger) }
    }
}
