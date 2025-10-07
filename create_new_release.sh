export APP_NAME="ftp-media-sync"

export BASE="/opt/$APP_NAME"

# update version

export TAG="v1.26"

export REL="$BASE/releases/$(date +%Y%m%d_%H%M%S)_$TAG"

git tag -a "$TAG" -m "Release $TAG"

git push origin "$TAG"

export REL="$BASE/releases/$(date +%Y%m%d_%H%M%S)_$TAG"

rsync -a --exclude venv --exclude .git ./ "$REL/"

source venv/bin/activate

python3 -m venv "$REL/venv"

source "$REL/venv/bin/activate"

pip install -r "$REL/backend/requirements.txt"

ln -sfn $REL /opt/ftp-media-sync/current

brew services restart caddy
