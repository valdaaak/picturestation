// SPDX-License-Identifier: GPL-3.0-or-later
package org.picturestation.app.ui.admin

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.ScrollableTabRow
import androidx.compose.material3.Tab
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import org.picturestation.app.AdminTab
import org.picturestation.app.AppViewModel
import org.picturestation.app.R
import org.picturestation.app.ui.Amber
import org.picturestation.app.ui.Muted
import org.picturestation.app.ui.Navy
import org.picturestation.app.ui.Paper

/** The tabs this version has; the others follow in the next versions. */
private val IMPLEMENTED = setOf(AdminTab.TV, AdminTab.USERS, AdminTab.GROUPS, AdminTab.GUEST)

@Composable
fun tabLabel(t: AdminTab): String = stringResource(when (t) {
    AdminTab.TV -> R.string.tab_tv
    AdminTab.USERS -> R.string.tab_users
    AdminTab.GROUPS -> R.string.tab_groups
    AdminTab.GUEST -> R.string.tab_guest
    AdminTab.SHARES -> R.string.tab_shares
    AdminTab.GENERAL -> R.string.tab_general
    AdminTab.MOVES -> R.string.tab_moves
    AdminTab.GALLERIES -> R.string.galleries
})

/** The administration of the active gallery: what the web gallery's Settings offer, as tabs. */
@Composable
fun AdminScreen(vm: AppViewModel) {
    val st = vm.admin ?: return
    LaunchedEffect(Unit) { vm.adminReload() }
    val info = st.info
    val tabs = AdminTab.entries.filter { it in IMPLEMENTED && (!it.mainOnly || info?.isMain == true) }
    val selected = tabs.indexOf(st.tab).coerceAtLeast(0)
    AdminScaffold(title = stringResource(R.string.admin), onBack = { vm.pop() }) { pad ->
        Column(modifier = Modifier.fillMaxSize().padding(pad)) {
            ScrollableTabRow(selectedTabIndex = selected, containerColor = Navy, contentColor = Paper, edgePadding = 8.dp) {
                tabs.forEach { t ->
                    Tab(selected = st.tab == t, onClick = { st.tab = t; vm.adminLoadTab(t) }, text = { Text(tabLabel(t)) },
                        selectedContentColor = Amber, unselectedContentColor = Muted)
                }
            }
            if (info == null) EmptyOrError(st.loading, st.error, null) { vm.adminReload() }
            else when (st.tab) {
                AdminTab.TV -> TvTab(vm, st, info)
                AdminTab.USERS -> UsersTab(vm, st, info)
                AdminTab.GROUPS -> GroupsTab(vm, st, info)
                AdminTab.GUEST -> GuestTab(vm, st, info)
                else -> MutedText(stringResource(R.string.admin_soon), Modifier.padding(16.dp))
            }
        }
    }
}
