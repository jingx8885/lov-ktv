package com.lovktv.tv.room

import com.lovktv.tv.room.RoomSync
import org.junit.Assert.assertFalse
import org.junit.Test

class RoomSyncTest {
    @Test
    fun cloudSnapshotNeverReplacesLanQueue() {
        assertFalse(RoomSync.shouldImportCloud(localQueueSize = 2, remoteQueueSize = 1))
        assertFalse(RoomSync.shouldImportCloud(localQueueSize = 0, remoteQueueSize = 1))
        assertFalse(RoomSync.shouldImportCloud(localQueueSize = 1, remoteQueueSize = 0))
        assertFalse(RoomSync.shouldImportCloud(localQueueSize = 0, remoteQueueSize = 0))
    }
}
