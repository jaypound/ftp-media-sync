iexport APP_NAME="ftp-media-sync"
export BASE="/opt/$APP_NAME"

# update version

export TAG="v1.1"
export REL="$BASE/releases/$(date +%Y%m%d_%H%M%S)_$TAG"

echo ln -sfn /opt/ftp-media-sync/releases/20250902_102744_v1.1 /opt/ftp-media-sync/current
