# Learning history and undo

Open the Angel Memory dashboard and choose the new **学习记录 (Learning history)** sidebar entry. **记忆浏览 (Memory browser)** still shows current memories. Learning history shows the source and before/after snapshots of newly recorded create, correction, and merge operations.

Filter by the exact chat memory scope and expand **查看来源与变更 (Source and changes)** to inspect the session, source excerpt, and snapshots. Missing historical sources are shown as unavailable and are never reconstructed.

Choose **撤销本次学习 (Undo this learning)**, review the record, scope, and affected counts, then check the acknowledgement and confirm. If affected memories have since changed, merged, or been deleted, undo is refused and the current content is preserved. Close the conflict dialog to refresh the records.

**已撤销 · 待同步 (Undone, index pending)** means the stored memories have been restored but their search index still needs synchronization. Inspect the visible error and choose **重试同步 (Retry synchronization)** on that record. Retrying does not apply the memory restoration again.

The page uses the dashboard's existing administrator access controls. Records may include source excerpts and should receive the same access protection as memories.
