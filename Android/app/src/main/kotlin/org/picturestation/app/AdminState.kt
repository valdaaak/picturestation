// SPDX-License-Identifier: GPL-3.0-or-later
package org.picturestation.app

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import org.picturestation.app.data.AdminInfo
import org.picturestation.app.data.Device
import org.picturestation.app.data.GalleriesList
import org.picturestation.app.data.MovesState
import org.picturestation.app.data.Share

/** The tabs of the administration screen, in the web's order but with the TV first (approving a code from a TV
 *  is what a phone does most). `mainOnly`: shown in the main gallery only. */
enum class AdminTab(val mainOnly: Boolean = false) { TV, USERS, GROUPS, GUEST, SHARES, GENERAL, MOVES, GALLERIES(mainOnly = true) }

/** What the administration screen holds while it is open: the gallery's state and the lazily loaded lists. */
class AdminState {
    var info by mutableStateOf<AdminInfo?>(null)
    var loading by mutableStateOf(false)
    var error by mutableStateOf<String?>(null)
    var tab by mutableStateOf(AdminTab.TV)
    var busy by mutableStateOf(false)
    var devices by mutableStateOf<List<Device>?>(null)
    var shares by mutableStateOf<List<Share>?>(null)
    var moves by mutableStateOf<MovesState?>(null)
    var galleries by mutableStateOf<GalleriesList?>(null)
}
