package com.lovktv.tv

/** LAN HostServer is the room source of truth. Cloud snapshots must not replace it. */
object RoomSync {
    /**
     * Phone Desk loads LAN m.html and writes the box queue. A 2s pull from
     * ktv.lovbrowser.com was importing that cloud room and wiping enqueue / undeleting skip.
     */
    @Suppress("UNUSED_PARAMETER")
    fun shouldImportCloud(localQueueSize: Int, remoteQueueSize: Int): Boolean {
        return false
    }
}
