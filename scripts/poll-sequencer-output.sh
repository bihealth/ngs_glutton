#!/usr/bin/env bash

# Polling of sequencer output directories.
#
# Assumptions:
#
# - conda env with ngs-glutton is loaded
# - conda env cubi_demux is available

# Print usage of the script.

usage()
{
    echo "Poll Sequencer Output Directory"
    echo "-------------------------------"
    echo ""
    echo "USAGE: poll-sequencer-output.sh -w WORK_DIR DIR [DIR ...]"
    echo ""
    echo "  -h      print this help"
    echo "  -w DIR  path to working directory (for locks and status files)."
    echo "  -o OP   Instrument operator to use on creation"
    echo "  -m INT  Max depth to search for (default: 3)"
    echo "  -y YEAR Year to start at (default: current)"
    echo ""
}

# Helper for logging

log_info()
{
    logger -t poll-seq-dir -s -p info -- $@
}

log_warn()
{
    logger -t poll-seq-dir -s -p warn -- $@
}

log_err()
{
    logger -t poll-seq-dir -s -p err -- $@
}

# Helper for generating status files

status_date()
{
    if [[ $1 -eq 0 ]]; then
        echo -e "SUCCESS\t$(date)"
    else
        echo -e "FAILURE\t$(date)"
    fi
}

# Parse command line arguments (named and positional).

OPERATOR=
WORK_DIR=
MAX_DEPTH=3
MIN_YEAR=$(date +%Y)
VERBOSE=

while [ ${#} -gt 0 ]; do
    OPTERR=0
    OPTIND=1
    getopts ":w:vm:y:o:" arg

    case "$arg" in
        h)
            usage
            exit 0
            ;;
        w)
            WORK_DIR=$(readlink -f "$OPTARG")
            ;;
        o)
            OPERATOR="$OPTARG"
            ;;
        m)
            MAX_DEPTH="$OPTARG"
            ;;
        y)
            MIN_YEAR="$OPTARG"
            ;;
        v)
            VERBOSE=-v
            ;;
        :)
            >&2 echo "ERROR: -$OPTARG requires an argument"
            >&2 echo
            >&2 usage
            exit 1
            ;;
        \?)
            SET+=("$1")
            ;;
        *)
            >&2 echo "ERROR -$arg unknown"
            >&2 echo
            >&2 usage
            ;;
    esac

    shift
    [[ "" != "$OPTARG" ]] && shift
done
[ ${#SET[@]} -gt 0 ] && set "" "${SET[@]}" && shift

# Check args

test -z "$WORK_DIR" && { >&2 echo "Option -w must be set!"; >&2 usage; exit 1; }
test -z "$OPERATOR" && { >&2 echo "Option -o must be set!"; >&2 usage; exit 1; }
test "$MAX_DEPTH" -lt 1 && { >&2 echo "Max. depth too low!"; >&2 usage; exit 1; }
test "$MIN_YEAR" -lt 2000 && { >&2 echo "Min. year too small!"; >&2 usage; exit 1; }

# Prepare everything

prepare()
{
    if [[ ! -e "$WORK_DIR" ]]; then
        log_info "Creating work directory $WORK_DIR"
        mkdir -p $WORK_DIR
    else
        log_info "Work directory $WORK_DIR already exists!"
    fi
}

prepare

# Get status from run folder

get-status()
{
    path="$1"

    2>/dev/null \
    ngs-glutton \
        $VERBOSE \
        -r "$path" \
        get-status
}

# Update the status

update-status()
{
    path="$1"

    ngs-glutton \
        $VERBOSE \
        -r "$path" \
        update-status \
        --status-category $2 \
        --status-value $3
}

# Flow cell information extraction

extract-data()
{
    path="$1"

    ngs-glutton \
        $VERBOSE \
        -r "$path" \
        extract \
        --operator "$OPERATOR" \
        --extract-planned-reads \
        --extract-reads
}

# Retrieve the sample sheet

retrieve-sample-sheet()
{
    path="$1"
    work_dir="$2"

    ngs-glutton \
        $VERBOSE \
        -r "$path" \
        retrieve-sample-sheet \
        --output-path "$work_dir/sample_sheet.yaml"
}

# Retrieve status

retrieve-status()
{
    path="$1"

    ngs-glutton \
        $VERBOSE \
        -r "$path" \
        retrieve-status \
        --status-category $2
}

# Retrieve lane count

retrieve-lane-count()
{
    path="$1"

    ngs-glutton \
        $VERBOSE \
        -r "$path" \
        retrieve-lane-count
}

# Retrieve delivery-type

retrieve-delivery-type()
{
    path="$1"

    ngs-glutton \
        $VERBOSE \
        -r "$path" \
        retrieve-delivery-type
}

# Perform the demultiplexing

run-demux()
{
    path="$1"
    work_dir="$2"

    (
        source activate cubi_demux
        cubi-demux \
            --verbose \
            --input-dir "$path" \
            --sample-sheet "$work_dir/sample_sheet.yaml" \
            --output-dir "$work_dir/DEMUX_RESULTS" \
            --cores 16 \
            --continue
    )
}

# Process run directory

test -z "$VERBOSE" || set -x

process-run-dir()
{
    path="$1"
    base_path="$(dirname "$1")"
    run_name="$(basename "$1")"

    date=$(echo $run_name | cut -d _ -f 1)
    year=20$(echo $date | cut -b 1,2)
    instrument=$(echo $run_name | cut -d _ -f 2)
    run_no=$(echo $run_name | cut -d _ -f 3)
    vendor_id=$(echo $run_name | cut -d _ -f 4)

    if [[ $year -lt $MIN_YEAR ]]; then
        log_info "Skipping $run_name because year before $MIN_YEAR"
        return
    fi

    work_dir="$WORK_DIR/$year/$run_name"
    log_info "Locking work directory $work_dir"
    mkdir -p "$work_dir"
    (
        flock -n 200  # waits for lock for 10 seconds by default

        # We update the flow cell via the API as long as we have not seen the
        # RTAComplete.txt marker file yet.  Once we see it, we update the
        # files a last time and then wait for the sample sheet to trigger
        # demultiplexing.  When we are done with demultiplexing, we will
        # update the status and submit a message with the quality report.

        # Import the run information until the sequencing is done.
        if [[ ! -e "$work_dir/STATUS_RTA_DONE" ]]; then
            log_info "Run not marked as complete yet; updating data..."
            extract-data "$path"

            status=$(get-status $path)
            [[ $? -eq 0 ]] || { >&2 echo "get-status failed!"; exit 1; }
            case $status in
                complete)
                    status_date 0 >$work_dir/STATUS_RTA_DONE
                    ;;
                failed)
                    status_date 1 >$work_dir/STATUS_RTA_DONE
                    ;;
                *)
                    >&2 echo "foo?! $status"
                    ;;
            esac
        fi

        # Kick off demultiplexing if sequencing is done.
        if [[ -e "$work_dir/STATUS_RTA_DONE" ]] && [[ ! -e "$work_dir/STATUS_DEMUX_DONE" ]] && \
                [[ "$conversion_status" != "skipped" ]]; then
            log_info "Run done but not demultiplexed; start demultiplexing..."
            update-status "$path" conversion in_progress

            log_info "Retrieving sample sheet"
            retrieve-sample-sheet "$path" "$work_dir"
            if [[ -s "$work_dir/sample_sheet.yaml" ]]; then
                log_info "Flow cell has no sample sheet (yet), skip conversion"
                update-status "$path" conversion skipped
            else
                # log_info "Creating configuration file"
                log_info "Starting demultiplexing"
                run-demux "$path" "$work_dir"
                ret=$?

                log_info "Demultiplexing complete with retval $?"
                if [[ $ret -eq 0 ]]; then
                    update-status "$path" conversion complete
                else
                    update-status "$path" conversion failed
                fi
                status_date $ret >$work_dir/STATUS_DEMUX_DONE
            fi
        fi

        # Kick off creation of raw data archives/tarballs after sequencing is
        # done.
        if [[ -e "$work_dir/STATUS_RTA_DONE" ]] && retrieve-delivery-type "$path" | grep bcl && \
                [[ ! -e "$work_dir/STATUS_RAW_ARCHIVES_DONE" ]]; then
            log_info "Creating raw base call archives"
            mkdir -p "$work_dir/RAW_ARCHIVES"

            ret=0
            for lane in $(eval "echo {1..$(retrieve-lane-count "$path")}"); do
                log_info "Creating tarball for lane $lane"

                # Build other-lane exclusion pattern.
                pattern=
                for l in $(eval "echo {1..$(retrieve-lane-count "$path")}"); do
                    if [[ $l -ne $lane ]]; then
                        pattern+=$(printf "/L%03d/|" $l)
                    fi
                done
                pattern=$(echo "$pattern" | sed -e 's/|$//')

                # Create tarball with all files excluding thumbnails and all
                # data information from other lanes.
                find "$path" -type f \
                | egrep -v Thumbnail_Images \
                | egrep -v "$pattern" \
                | tar \
                    --exclude Thumbnail_Images \
                    -czf "$work_dir/RAW_ARCHIVES/${run_name}_LANE_$lane.tar.gz" \
                    -C "$base_path" \
                    --files-from -

                pushd "$work_dir/RAW_ARCHIVES"
                md5sum ${run_name}_LANE_$lane.tar.gz >${run_name}_LANE_$lane.tar.gz.md5
                popd

                let "ret=$ret+$?"
            done
            status_date $ret >"$work_dir/STATUS_RAW_ARCHIVES_DONE"
        fi
    ) 200>"$work_dir/.flock"
    log_info "Released lock again"
}

# Start search below all input paths.

for path in $@; do
    log_info "Looking in $path"
    while IFS= read -r -d $'\0' file; do
        process-run-dir "$(dirname "$file")"
    done < <(find "$path" -maxdepth $MAX_DEPTH -name RunInfo.xml -print0)
done