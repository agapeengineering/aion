#!/bin/sh
set -eu
umask 077

: "${AION_BACKUP_BUCKET:?Set the private database backup bucket}"
: "${AION_RECOVERY_BUCKET:?Set the private independently retained marker bucket}"
: "${AION_RECOVERY_REGION:?Set the AWS region}"
: "${AION_RECOVERY_ACCOUNT:?Set the AWS bucket owner account ID}"
: "${AION_STAGING_RELEASE_DIR:?Set the installed release directory}"
: "${AION_STAGING_STATE_DIR:?Set the installed private state directory}"
: "${AION_RECOVERY_WORK_DIR:?Set an owner-private directory for temporary captures}"
: "${AION_RECOVERY_RSA_KEY:?Set the operator public encryption certificate}"

kind="${1:-}"
case "$kind" in
    snapshot|markers) ;;
    *) printf '%s\n' 'Usage: backup.sh snapshot|markers' >&2; exit 2 ;;
esac
if [ "$#" -ne 1 ]; then
    printf '%s\n' 'Usage: backup.sh snapshot|markers' >&2
    exit 2
fi
if [ "$kind" = snapshot ]; then
    : "${AION_KEY_BACKUP_BUCKET:?Set the operator-only configuration key bucket}"
fi

install -d -m 0700 "$AION_RECOVERY_WORK_DIR"
cd "$(dirname "$0")"
exec 9>"$AION_RECOVERY_WORK_DIR/$kind.lock"
flock -x -w 45 9
work=$(mktemp -d "$AION_RECOVERY_WORK_DIR/capture.XXXXXXXX")
trap 'rm -r -- "$work"' EXIT
trap 'exit 1' HUP INT TERM

project=${AION_RECOVERY_SOURCE_PROJECT:-aion-staging}
python3 ./capture.py "$kind" "$AION_STAGING_RELEASE_DIR" "$AION_STAGING_STATE_DIR" "$work/data" \
    --project "$project"
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
object="$timestamp-${work##*.}"
if [ "$project" != aion-staging ]; then
    object="drills/$project/$object"
fi

aws() {
    # The role stays on this EC2 instance. Only the temporary capture directory is mounted.
    docker run --rm --pull=never --network host \
        -e AWS_PAGER= -e AWS_MAX_ATTEMPTS=3 -e AWS_METADATA_SERVICE_NUM_ATTEMPTS=3 \
        -v "$work/data:/aws" \
        docker.io/amazon/aws-cli:2.32.0@sha256:4090597cd26166b53219e6e6d40c0267681a7c9a8b69e1d92722ff5a0cd6705a \
        --region "$AION_RECOVERY_REGION" "$@"
}

upload() {
    aws s3api put-object --bucket "$1" --key "$2" --body "$3" \
        --if-none-match '*' --server-side-encryption AES256 --checksum-algorithm SHA256 \
        --expected-bucket-owner "$AION_RECOVERY_ACCOUNT" \
        --query '[ETag,ChecksumSHA256]' --output text >/dev/null
}

if [ "$kind" = markers ]; then
    upload "$AION_RECOVERY_BUCKET" "markers/$object.json" markers.json
    printf 'Stored independent markers %s\n' "markers/$object.json"
else
    openssl cms -encrypt -binary -aes-256-cbc -outform DER \
        -in "$work/data/keys.tar.gz" -out "$work/data/keys.cms" "$AION_RECOVERY_RSA_KEY"
    upload "$AION_KEY_BACKUP_BUCKET" "keys/$object.cms" keys.cms
    upload "$AION_BACKUP_BUCKET" "snapshots/$object.tar.gz" snapshot.tar.gz
    printf 'Stored database and encrypted key backups %s\n' "$object"
fi
if [ "$project" = aion-staging ]; then
    case "$kind" in
        snapshot) metric=DatabaseSnapshot ;;
        markers) metric=IndependentMarkers ;;
    esac
    aws cloudwatch put-metric-data --namespace Aion/StagingRecovery \
        --metric-data "MetricName=$metric,Value=1,Unit=Count"
fi
