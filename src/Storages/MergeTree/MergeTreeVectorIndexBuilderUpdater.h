#pragma once

#include <atomic>
#include <functional>
#include <map>
#include <mutex>

#include <Columns/ColumnArray.h>
#include <Columns/IColumn.h>
#include <Storages/MergeTree/IMergedBlockOutputStream.h>
#include <Storages/MergeTree/MarkRange.h>
#include <Storages/MergeTree/MergeAlgorithm.h>
#include <Storages/MergeTree/MergeTreeData.h>
#include <Storages/MergeTree/MergeTreeSequentialSource.h>
#include <Storages/MergeTree/MergeType.h>
#include <Storages/MergeTree/TTLMergeSelector.h>
#include <Storages/MergeTree/VectorIndexEntry.h>
#include <Storages/VectorIndexCommands.h>
#include <VectorIndex/Dataset.h>
#include <VectorIndex/VectorSegmentExecutor.h>
#include <VectorIndex/Status.h>
#include <Common/logger_useful.h>
#include <VectorIndex/MergeUtils.h>
#include <Common/ActionBlocker.h>

namespace DB
{

enum class BuildVectorIndexStatus
{
    NO_DATA_PART = 0,
    SUCCESS = 1,
    BUILD_FAIL = 2,
    META_ERROR = 3,
    MISCONFIGURED = 4,
    BUILD_SKIPPED = 5,  /// No need to build vector index for this part
    BUILD_RETRY = 6, /// Retry to move vector index files to part directory
};

class MergeTreeVectorIndexBuilderUpdater
{
public:
    MergeTreeVectorIndexBuilderUpdater(MergeTreeData & data_);

    /// Check backgroud pool size for vector index if new log entry is allowed.
    /// True if allowed to select part for build vector index.
    bool allowToBuildVectorIndex(const bool slow_mode, const size_t builds_count_in_queue) const;

    /// Select a part without vector index to build vector index
    /// In multiple vectors case, choose a part without a vector index in metadata.
    VectorIndexEntryPtr selectPartToBuildVectorIndex(
        const StorageMetadataPtr & metadata_snapshot,
        bool select_slow_mode_part,
        const MergeTreeData::DataParts & currently_merging_mutating_parts = {});

    void removeDroppedVectorIndices(const StorageMetadataPtr & metadata_snapshot);

    /// handle build index task
    BuildVectorIndexStatus buildVectorIndex(
        const StorageMetadataPtr & metadata_snapshot,
        const String & part_name,
        const String & vector_index_name,
        bool slow_mode);

    /** Is used to cancel all index builds. On cancel() call all currently running actions will throw exception soon.
      * All new attempts to start a vector index build will throw an exception until all 'LockHolder' objects will be destroyed.
      */
    ActionBlocker builds_blocker;

private:
    MergeTreeData & data;
    bool is_replicated = false; /// Mark if replicated
    //const size_t background_pool_size;

    Poco::Logger * log;

    time_t last_cache_check_time = 0;

    BuildVectorIndexStatus
    buildVectorIndexForOnePart(const StorageMetadataPtr & metadata_snapshot, const MergeTreeDataPartPtr & part, const String & vector_index_name, bool slow_mode);

    /// Find furture part and do some checks before move vector index files.
    /// Used for first build or retry to move if first build failed to move.
    BuildVectorIndexStatus TryMoveVectorIndexFiles(
        const MergeTreeDataPartPtr & build_part,
        const VectorIndexDescription & vec_index_desc,
        DiskPtr disk,
        const String & vector_tmp_relative_path,
        const UInt64 & dim,
        VectorIndex::VectorSegmentExecutorPtr vec_index_builder = nullptr);

    /// Move build vector index files from temporary directory to data part directory, and apply lightweight delete if needed.
    /// And finally write vector index checksums file.
    bool moveVectorIndexFilesToFuturePartAndCache(
        DiskPtr disk,
        const String & vector_tmp_relative_path,
        const MergeTreeDataPartPtr & dest_part,
        const VectorIndexDescription & vec_index_desc,
        const VectorIndex::VectorSegmentExecutorPtr vec_executor);

    bool isSlowModePart(const MergeTreeDataPartPtr & part, const String & index_name)
    {
        /// Smaller part built with single vector index is also treated as slow mode.
        return part->containRowIdsMaps(index_name) || part->rows_count < data.getSettings()->max_rows_for_slow_mode_single_vector_index_build;
    }
};

}
